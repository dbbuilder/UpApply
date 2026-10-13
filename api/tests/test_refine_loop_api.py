"""API tests for the refine + final endpoints (LLM, embeddings and extraction mocked)."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.cover_letter import CoverLetter
from app.models.fact import Fact
from app.models.job import Job
from app.models.proposal import Proposal
from app.schemas.fact import FactCandidate
from app.services.generation.refine import RefineError, RefineResult
from app.services.generation.writer import Draft
from tests.conftest import TestSessionLocal

JOBS = "app.api.v1.jobs"
BRIEF = {
    "needs": ["has migrated prod SQL Server to Azure without downtime"],
    "job_types": ["cloud", "sql"],
    "client_signals": {},
    "mirror_phrases": [],
    "explicit_asks": [],
    "questions": ["What is your migration approach?"],
}
ORIGINAL = (
    "Zero downtime is the whole job here. The 160-server Azure move ran with no outage "
    "because every cutover had a rehearsed rollback.\n\nWarm regards,\nChris"
)


async def _user_id(client: AsyncClient, headers: dict) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


async def _seed_fact(user_id: str, statement: str) -> str:
    async with TestSessionLocal() as s:
        fact = Fact(
            user_id=user_id, kind="project", statement=statement, detail=None,
            skills=["Azure"], industries=[], job_types=["cloud"], strength=0.9,
            status="approved", source_type="bio_memory", source_ref=None, sources=[],
            times_used=0, times_in_won=0, embedding=[0.1] * 1536,
        )
        s.add(fact)
        await s.commit()
        return str(fact.id)


async def _seed_letter(user_id: str, *, brief: dict | None = BRIEF, fact_ids=None) -> tuple[str, str]:
    async with TestSessionLocal() as s:
        job = Job(
            user_id=user_id, upwork_url="https://www.upwork.com/jobs/~01abc",
            title="Azure SQL migration lead",
            description="Move our SQL Server estate to Azure without downtime.",
            skills_required=["Azure", "SQL Server"],
        )
        s.add(job)
        await s.flush()
        letter = CoverLetter(
            user_id=user_id, job_id=job.id, content=ORIGINAL, model_used="claude-opus-5-5",
            brief=brief, fact_ids_used=fact_ids or [], voice_sample_ids=[], version=1,
        )
        s.add(letter)
        await s.commit()
        return job.id, letter.id


async def _letter(letter_id: str) -> CoverLetter:
    async with TestSessionLocal() as s:
        return (await s.execute(select(CoverLetter).where(CoverLetter.id == letter_id))).scalar_one()


@pytest.mark.asyncio
async def test_refine_updates_letter_thread_and_facts(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    used_id = await _seed_fact(uid, "Led a 160-server on-prem to Azure migration.")
    found_id = await _seed_fact(uid, "Built AnalyzeMyCloud.com for Azure cost analysis.")
    _, letter_id = await _seed_letter(uid, fact_ids=[used_id])

    async with TestSessionLocal() as s:
        found_fact = (await s.execute(select(Fact).where(Fact.id == found_id))).scalar_one()
    revised = "Zero downtime, proven on Azure, with cost analysis built in.\n\nWarm regards,\nChris"
    result = RefineResult(
        draft=Draft(
            cover_letter=revised,
            screening_answers=[{"question": "What is your migration approach?", "answer": "Phased cutover."}],
            fact_ids_used=[used_id, found_id, "not-a-real-fact"],
        ),
        warnings=["Sentence starts with 'I'"],
        found_facts=[found_fact],
    )
    cand = FactCandidate(kind="metric", statement="The Azure migration covered 160 servers.",
                         source_type="refine_thread")
    with patch(f"{JOBS}.refine_application", AsyncMock(return_value=result)) as refine, \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[cand])) as extract, \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()) as upsert:
        r = await client.post(
            f"/api/v1/jobs/cover-letters/{letter_id}/refine",
            headers=auth_headers_with_profile,
            json={"message": "It was 160 servers, and mention the cost work",
                  "screening_answers": [{"question": "What is your migration approach?", "answer": "Big bang."}]},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cover_letter"] == revised
    assert body["warnings"] == ["Sentence starts with 'I'"]
    assert body["screening_answers"][0]["answer"] == "Phased cutover."
    assert [m["role"] for m in body["refine_messages"]] == ["user", "assistant"]

    current = refine.await_args.args[5]
    assert current.cover_letter == ORIGINAL
    assert current.screening_answers == [{"question": "What is your migration approach?", "answer": "Big bang."}]
    assert refine.await_args.args[7] == "It was 160 servers, and mention the cost work"
    extract.assert_awaited_once()
    assert extract.await_args.args[1] == "refine_thread"
    upsert.assert_awaited_once()

    letter = await _letter(letter_id)
    assert letter.content == revised
    assert {str(x) for x in letter.fact_ids_used} == {used_id, found_id}
    assert len(letter.refine_messages) == 2
    async with TestSessionLocal() as s:
        times = dict((await s.execute(select(Fact.id, Fact.times_used))).all())
    assert times[found_fact.id] == 1          # newly used via search_facts
    assert sum(times.values()) == 1           # the already-used fact is not double counted


@pytest.mark.asyncio
async def test_second_turn_uses_answers_from_thread(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    async with TestSessionLocal() as s:
        letter = (await s.execute(select(CoverLetter).where(CoverLetter.id == letter_id))).scalar_one()
        letter.refine_messages = [
            {"role": "user", "content": "shorter", "at": "2026-10-12T00:00:00+00:00"},
            {"role": "assistant", "content": ORIGINAL, "warnings": [], "at": "2026-10-12T00:00:00+00:00",
             "screening_answers": [{"question": "What is your migration approach?", "answer": "From thread."}]},
        ]
        await s.commit()

    result = RefineResult(draft=Draft(cover_letter=ORIGINAL, screening_answers=[], fact_ids_used=[]),
                          warnings=[], found_facts=[])
    with patch(f"{JOBS}.refine_application", AsyncMock(return_value=result)) as refine, \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])), \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()):
        r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                              headers=auth_headers_with_profile,
                              json={"message": "warmer", "screening_answers": [
                                  {"question": "What is your migration approach?", "answer": "Ignored."}]})
    assert r.status_code == 200, r.text
    assert refine.await_args.args[5].screening_answers[0]["answer"] == "From thread."
    assert len(refine.await_args.args[6]) == 2
    assert len(r.json()["refine_messages"]) == 4


@pytest.mark.asyncio
async def test_refine_rejects_non_v2_letter(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid, brief=None)
    r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                          headers=auth_headers_with_profile, json={"message": "shorter"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_refine_blank_message_and_unknown_letter(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                          headers=auth_headers_with_profile, json={"message": "   "})
    assert r.status_code == 422
    r = await client.post("/api/v1/jobs/cover-letters/00000000-0000-0000-0000-000000000000/refine",
                          headers=auth_headers_with_profile, json={"message": "shorter"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_refine_model_failure_is_502(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    with patch(f"{JOBS}.refine_application", AsyncMock(side_effect=RefineError("declined"))):
        r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                              headers=auth_headers_with_profile, json={"message": "shorter"})
    assert r.status_code == 502
    assert (await _letter(letter_id)).refine_messages is None


@pytest.mark.asyncio
async def test_fact_capture_failure_does_not_break_refine(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    result = RefineResult(draft=Draft(cover_letter="New text.\n\nWarm regards,\nChris",
                                      screening_answers=[], fact_ids_used=[]),
                          warnings=[], found_facts=[])
    with patch(f"{JOBS}.refine_application", AsyncMock(return_value=result)), \
         patch(f"{JOBS}.extract_facts", AsyncMock(side_effect=RuntimeError("haiku down"))):
        r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                              headers=auth_headers_with_profile, json={"message": "shorter"})
    assert r.status_code == 200, r.text
    assert (await _letter(letter_id)).content.startswith("New text.")


@pytest.mark.asyncio
async def test_refine_failure_returns_generic_error_body(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    exc = RefineError("Refine API error: secret upstream text", reason="api_error")
    with patch(f"{JOBS}.refine_application", AsyncMock(side_effect=exc)):
        r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                              headers=auth_headers_with_profile, json={"message": "shorter"})
    assert r.status_code == 502
    body = r.json()
    assert body["code"] == "generation_unavailable"
    assert body["request_id"]
    assert "secret upstream text" not in r.text


@pytest.mark.asyncio
async def test_refine_foreign_letter_is_404(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    other = await client.post("/api/v1/auth/register",
                              json={"email": "other@example.com", "password": "testpass123"})
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    with patch(f"{JOBS}.refine_application", AsyncMock()) as refine:
        r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                              headers=headers, json={"message": "shorter"})
    assert r.status_code == 404
    refine.assert_not_awaited()


@pytest.mark.asyncio
async def test_refine_message_too_long_is_422(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                          headers=auth_headers_with_profile, json={"message": "x" * 4001})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_refine_surfaces_claims_verified_and_trims_thread(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    async with TestSessionLocal() as s:
        letter = (await s.execute(select(CoverLetter).where(CoverLetter.id == letter_id))).scalar_one()
        letter.refine_messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}", "at": "x",
             **({} if i % 2 == 0 else {"screening_answers": [], "warnings": []})}
            for i in range(20)
        ]
        await s.commit()

    result = RefineResult(draft=Draft(cover_letter=ORIGINAL, screening_answers=[], fact_ids_used=[]),
                          warnings=["CLAIM_CHECK_SKIPPED"], found_facts=[], claims_verified=False)
    with patch(f"{JOBS}.refine_application", AsyncMock(return_value=result)), \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])), \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()):
        r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                              headers=auth_headers_with_profile, json={"message": "warmer"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["claims_verified"] is False
    assert len(body["refine_messages"]) == 20
    assert body["refine_messages"][-2]["content"] == "warmer"
    assert len((await _letter(letter_id)).refine_messages) == 20


async def _extension_proposal(user_id: str, job_id: str) -> Proposal | None:
    async with TestSessionLocal() as s:
        return (await s.execute(select(Proposal).where(
            Proposal.user_id == user_id, Proposal.job_id == job_id, Proposal.source == "extension",
        ))).scalars().first()


@pytest.mark.asyncio
async def test_final_light_edit_is_chris_edited_ai(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    job_id, letter_id = await _seed_letter(uid)
    edited = ORIGINAL.replace("rehearsed rollback", "rehearsed and timed rollback")
    with patch(f"{JOBS}.generate_embedding", AsyncMock(return_value=[0.2] * 1536)) as embed, \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[
             FactCandidate(kind="outcome", statement="No outage across 160 cutovers.",
                           source_type="upwork_submission")])) as extract, \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()) as upsert:
        r = await client.put(
            f"/api/v1/jobs/cover-letters/{letter_id}/final",
            headers=auth_headers_with_profile,
            json={"final_text": edited,
                  "final_answers": [{"question": "What is your migration approach?", "answer": "Phased."}]},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["author"] == "chris_edited_ai"
    assert 0 < body["edit_distance_pct"] < 0.9
    assert body["fact_candidates"] == 1
    assert embed.await_count == 2  # letter text + job text
    assert "Q: What is your migration approach?\nA: Phased." in extract.await_args.args[0]
    assert extract.await_args.args[1] == "upwork_submission"
    upsert.assert_awaited_once()

    letter = await _letter(letter_id)
    assert letter.final_text == edited
    assert letter.final_answers == [{"question": "What is your migration approach?", "answer": "Phased."}]
    assert letter.was_submitted is True and letter.is_final is True
    prop = await _extension_proposal(uid, job_id)
    assert prop.id == body["proposal_id"]
    assert prop.author == "chris_edited_ai"
    assert prop.screening_answers == [{"question": "What is your migration approach?", "answer": "Phased."}]
    assert prop.facts_ingested_at is not None
    assert prop.cover_letter_text == edited
    assert prop.job_text == "Move our SQL Server estate to Azure without downtime."
    assert prop.job_needs_embedding is not None


@pytest.mark.asyncio
async def test_final_rewrite_is_chris_and_repeat_is_idempotent(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    job_id, letter_id = await _seed_letter(uid)
    rewritten = ("Your estate sounds like the hospital network we moved last spring. "
                 "Happy to walk you through my plan on a call this week.\n\nThanks,\nC. Therriault")
    with patch(f"{JOBS}.generate_embedding", AsyncMock(return_value=[0.2] * 1536)), \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])) as extract, \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()):
        first = await client.put(f"/api/v1/jobs/cover-letters/{letter_id}/final",
                                 headers=auth_headers_with_profile, json={"final_text": rewritten})
        second = await client.put(f"/api/v1/jobs/cover-letters/{letter_id}/final",
                                  headers=auth_headers_with_profile, json={"final_text": rewritten})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["author"] == "chris"
    assert first.json()["edit_distance_pct"] >= 0.9
    assert extract.await_count == 1
    assert second.json()["proposal_id"] == first.json()["proposal_id"]
    async with TestSessionLocal() as s:
        count = len((await s.execute(select(Proposal).where(Proposal.job_id == job_id))).scalars().all())
    assert count == 1


@pytest.mark.asyncio
async def test_final_survives_embedding_outage(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    job_id, letter_id = await _seed_letter(uid)
    with patch(f"{JOBS}.generate_embedding", AsyncMock(side_effect=RuntimeError("quota"))), \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])), \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()):
        r = await client.put(f"/api/v1/jobs/cover-letters/{letter_id}/final",
                             headers=auth_headers_with_profile, json={"final_text": ORIGINAL})
    assert r.status_code == 200, r.text
    assert r.json()["edit_distance_pct"] == 0.0
    prop = await _extension_proposal(uid, job_id)
    assert prop.embedding is None and prop.job_needs_embedding is None


@pytest.mark.asyncio
async def test_final_unknown_letter_404(client, auth_headers_with_profile):
    r = await client.put("/api/v1/jobs/cover-letters/00000000-0000-0000-0000-000000000000/final",
                         headers=auth_headers_with_profile, json={"final_text": "x"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_final_foreign_letter_is_404_and_writes_nothing(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    job_id, letter_id = await _seed_letter(uid)
    other = await client.post("/api/v1/auth/register",
                              json={"email": "other@example.com", "password": "testpass123"})
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    with patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])) as extract:
        r = await client.put(f"/api/v1/jobs/cover-letters/{letter_id}/final",
                             headers=headers, json={"final_text": "hijacked"})
    assert r.status_code == 404
    extract.assert_not_awaited()
    assert (await _letter(letter_id)).final_text is None
    async with TestSessionLocal() as s:
        assert (await s.execute(select(Proposal).where(Proposal.job_id == job_id))).scalars().first() is None


@pytest.mark.asyncio
async def test_final_ignores_client_sent_author(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    job_id, letter_id = await _seed_letter(uid)
    with patch(f"{JOBS}.generate_embedding", AsyncMock(return_value=[0.2] * 1536)), \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])), \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()):
        r = await client.put(f"/api/v1/jobs/cover-letters/{letter_id}/final",
                             headers=auth_headers_with_profile,
                             json={"final_text": ORIGINAL, "author": "chris"})
    assert r.status_code == 200, r.text
    assert r.json()["author"] == "chris_edited_ai"
    assert (await _extension_proposal(uid, job_id)).author == "chris_edited_ai"


@pytest.mark.asyncio
async def test_final_rejects_oversized_text_and_answers(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    url = f"/api/v1/jobs/cover-letters/{letter_id}/final"
    too_long = await client.put(url, headers=auth_headers_with_profile, json={"final_text": "x" * 20001})
    too_many = await client.put(url, headers=auth_headers_with_profile, json={
        "final_text": "ok", "final_answers": [{"question": "q", "answer": "a"}] * 21})
    long_answer = await client.put(url, headers=auth_headers_with_profile, json={
        "final_text": "ok", "final_answers": [{"question": "q", "answer": "a" * 5001}]})
    assert too_long.status_code == too_many.status_code == long_answer.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
async def test_final_rejects_blank_text_and_writes_nothing(client, auth_headers_with_profile, blank):
    uid = await _user_id(client, auth_headers_with_profile)
    job_id, letter_id = await _seed_letter(uid)
    with patch(f"{JOBS}.generate_embedding", AsyncMock(return_value=[0.2] * 1536)) as embed, \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])) as extract:
        r = await client.put(f"/api/v1/jobs/cover-letters/{letter_id}/final",
                             headers=auth_headers_with_profile, json={"final_text": blank})
    assert r.status_code == 422
    embed.assert_not_awaited()
    extract.assert_not_awaited()
    letter = await _letter(letter_id)
    assert letter.final_text is None and letter.submitted_text is None
    assert await _extension_proposal(uid, job_id) is None


@pytest.mark.asyncio
async def test_final_concurrent_double_submit_does_not_duplicate(client, auth_headers_with_profile):
    """A double Submit click fires two PUTs at once; they must serialize on the letter row."""
    uid = await _user_id(client, auth_headers_with_profile)
    job_id, letter_id = await _seed_letter(uid)

    async def slow_embed(_text):
        await asyncio.sleep(0.05)  # let the other request reach the letter read
        return [0.2] * 1536

    with patch(f"{JOBS}.generate_embedding", AsyncMock(side_effect=slow_embed)), \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])) as extract, \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()):
        url = f"/api/v1/jobs/cover-letters/{letter_id}/final"
        first, second = await asyncio.gather(
            client.put(url, headers=auth_headers_with_profile, json={"final_text": ORIGINAL}),
            client.put(url, headers=auth_headers_with_profile, json={"final_text": ORIGINAL}),
        )
    assert first.status_code == 200 and second.status_code == 200, (first.text, second.text)
    assert extract.await_count == 1
    assert first.json()["proposal_id"] == second.json()["proposal_id"]
    async with TestSessionLocal() as s:
        props = (await s.execute(select(Proposal).where(Proposal.job_id == job_id))).scalars().all()
    assert len(props) == 1
