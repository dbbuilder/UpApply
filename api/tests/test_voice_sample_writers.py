"""Every Proposal writer tags author/outcome like migration 022 and fills job_needs_embedding."""
import io
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.application import Application, ApplicationStatus
from app.models.cover_letter import CoverLetter
from app.models.job import Job
from app.models.proposal import Proposal
from app.models.user import User
from tests.conftest import TestSessionLocal
from tests.vector_utils import unit


@pytest.fixture
def fake_embed():
    mock = AsyncMock(return_value=unit(5))
    with patch("app.api.v1.proposals.generate_embedding", mock), \
         patch("app.api.v1.jobs.generate_embedding", mock), \
         patch("app.api.v1.applications.generate_embedding", mock), \
         patch("app.api.v1.import_chatgpt.generate_embedding", mock):
        yield mock


async def _uid(client, headers) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


async def _seed_job_and_letter(uid: str) -> tuple[str, str]:
    async with TestSessionLocal() as s:
        job = Job(user_id=uid, upwork_url="https://www.upwork.com/jobs/~01x", title="Azure SQL migration",
                  description="Move 40 SQL servers to Azure", source="extension")
        s.add(job)
        await s.flush()
        letter = CoverLetter(user_id=uid, job_id=job.id, content="Draft letter", model_used="m")
        s.add(letter)
        await s.commit()
        return job.id, letter.id


async def _proposals(uid: str) -> list[Proposal]:
    async with TestSessionLocal() as s:
        return list((await s.execute(select(Proposal).where(Proposal.user_id == uid))).scalars().all())


@pytest.mark.asyncio
async def test_extension_submit_is_chris_edited_ai_with_job_embedding(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _uid(client, auth_headers)
    _, letter_id = await _seed_job_and_letter(uid)
    r = await client.put(f"/api/v1/jobs/cover-letters/{letter_id}/submit", headers=auth_headers,
                         json={"submitted_text": "Final edited letter"})
    assert r.status_code == 200
    [p] = await _proposals(uid)
    assert p.source == "extension"
    assert p.author == "chris_edited_ai"
    assert p.job_text == "Move 40 SQL servers to Azure"
    assert p.job_needs_embedding is not None
    assert "Azure SQL migration\n\nMove 40 SQL servers to Azure" in [c.args[0] for c in fake_embed.await_args_list]


@pytest.mark.asyncio
async def test_hired_outcome_promotion_sets_outcome_author_and_job_embedding(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _uid(client, auth_headers)
    job_id, letter_id = await _seed_job_and_letter(uid)
    async with TestSessionLocal() as s:
        app_row = Application(user_id=uid, job_id=job_id, cover_letter_id=letter_id, status=ApplicationStatus.SUBMITTED)
        s.add(app_row)
        await s.commit()
        app_id = app_row.id
    r = await client.put(f"/api/v1/applications/{app_id}/outcome", headers=auth_headers, json={"status": "hired"})
    assert r.status_code == 200
    [p] = await _proposals(uid)
    assert p.was_hired is True
    assert p.outcome == "hired"
    assert p.author == "chris_edited_ai"
    assert p.job_needs_embedding is not None


@pytest.mark.asyncio
async def test_backfill_proposals_tags_author_and_outcome(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _uid(client, auth_headers)
    job_id, letter_id = await _seed_job_and_letter(uid)
    async with TestSessionLocal() as s:
        s.add(Application(user_id=uid, job_id=job_id, cover_letter_id=letter_id, status=ApplicationStatus.HIRED))
        await s.commit()
    r = await client.post("/api/v1/applications/backfill-proposals", headers=auth_headers)
    assert r.json()["created"] == 1
    [p] = await _proposals(uid)
    assert p.author == "chris_edited_ai"
    assert p.outcome == "hired"
    assert p.job_needs_embedding is not None


@pytest.mark.asyncio
async def test_contract_import_letter_is_hired_with_job_embedding(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _uid(client, auth_headers)
    contract = {"contract_id": "c9", "title": "SQL tuning", "contract_type": "hourly", "status": "ended",
                "cover_letter_text": "Winning letter"}
    r = await client.post("/api/v1/jobs/import-contracts", headers=auth_headers, json={"contracts": [contract]})
    assert r.status_code == 200
    [p] = await _proposals(uid)
    assert p.outcome == "hired"
    assert p.job_needs_embedding is not None

    # Re-import of a pre-existing (un-tagged) row also gets the outcome.
    async with TestSessionLocal() as s:
        row = (await s.execute(select(Proposal).where(Proposal.id == p.id))).scalar_one()
        row.outcome = None
        row.job_needs_embedding = None
        await s.commit()
    await client.post("/api/v1/jobs/import-contracts", headers=auth_headers, json={"contracts": [contract]})
    [p] = await _proposals(uid)
    assert p.outcome == "hired"
    assert p.job_needs_embedding is not None


@pytest.mark.asyncio
async def test_chatgpt_import_tags_letters_as_ai(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _uid(client, auth_headers)
    conv = {"title": "Letter", "current_node": "b", "mapping": {
        "a": {"message": {"author": {"role": "user"}, "content": {"parts": ["Write a letter"]}}, "parent": None},
        "b": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["Here it is"]}}, "parent": "a"},
    }}
    extracted = {"memories": [], "proposals": ["A ChatGPT-written cover letter " * 10]}
    with patch("app.api.v1.import_chatgpt.AsyncAnthropic"), \
         patch("app.api.v1.import_chatgpt._extract_from_conversation", AsyncMock(return_value=extracted)):
        r = await client.post(
            "/api/v1/import/import-chatgpt-conversations", headers=auth_headers,
            files={"file": ("conversations.json", io.BytesIO(json.dumps([conv]).encode()), "application/json")},
        )
    assert r.status_code == 200, r.text
    [p] = await _proposals(uid)
    assert p.source == "chatgpt_import"
    assert p.author == "ai"


@pytest.mark.asyncio
async def test_backfill_job_embeddings_fills_voice_rows_only(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _uid(client, auth_headers)
    job_id, _ = await _seed_job_and_letter(uid)
    async with TestSessionLocal() as s:
        other = User(email="other-backfill@example.com", hashed_password="x")
        s.add(other)
        await s.flush()
        linked = Proposal(user_id=uid, job_id=job_id, cover_letter_text="L1", job_title="Azure SQL migration",
                          source="extension", author="chris_edited_ai")
        own_text = Proposal(user_id=uid, cover_letter_text="L2", job_title="CTO", job_text="Lead the team", source="scraped")
        ai = Proposal(user_id=uid, cover_letter_text="L3", job_title="AI", source="chatgpt_import", author="ai")
        theirs = Proposal(user_id=other.id, cover_letter_text="L4", job_title="Theirs", source="scraped")
        s.add_all([linked, own_text, ai, theirs])
        await s.commit()
        ids = {"linked": linked.id, "own": own_text.id, "ai": ai.id, "theirs": theirs.id}

    r = await client.post("/api/v1/proposals/backfill-job-embeddings", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"embedded": 2, "remaining": 0}
    texts = [c.args[0] for c in fake_embed.await_args_list]
    assert "Azure SQL migration\n\nMove 40 SQL servers to Azure" in texts
    assert "CTO\n\nLead the team" in texts
    async with TestSessionLocal() as s:
        rows = {p.id: p for p in (await s.execute(select(Proposal))).scalars().all()}
    assert rows[ids["linked"]].job_needs_embedding is not None
    assert rows[ids["own"]].job_needs_embedding is not None
    assert rows[ids["ai"]].job_needs_embedding is None
    assert rows[ids["theirs"]].job_needs_embedding is None


async def _seed_fact_on_letter(letter_id: str, uid: str) -> str:
    from app.models.fact import Fact

    async with TestSessionLocal() as s:
        fact = Fact(user_id=uid, kind="project", statement="Led a 160-server Azure migration.",
                    status="approved", source_type="bio_memory", sources=[], times_used=1, times_in_won=0)
        s.add(fact)
        await s.flush()
        letter = (await s.execute(select(CoverLetter).where(CoverLetter.id == letter_id))).scalar_one()
        letter.fact_ids_used = [str(fact.id)]
        await s.commit()
        return str(fact.id)


async def _times_in_won(fact_id: str) -> int:
    from app.models.fact import Fact

    async with TestSessionLocal() as s:
        return (await s.execute(select(Fact.times_in_won).where(Fact.id == fact_id))).scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_row", [False, True])
async def test_hired_outcome_promotion_credits_facts_once(client: AsyncClient, auth_headers: dict, fake_embed,
                                                         existing_row: bool):
    """A hire recorded in UpApply credits the letter's facts; a later Upwork sync never re-credits."""
    uid = await _uid(client, auth_headers)
    job_id, letter_id = await _seed_job_and_letter(uid)
    fact_id = await _seed_fact_on_letter(letter_id, uid)
    async with TestSessionLocal() as s:
        if existing_row:
            s.add(Proposal(user_id=uid, job_id=job_id, cover_letter_text="Final", job_title="Azure SQL migration",
                           source="extension", author="chris_edited_ai", upwork_proposal_id="777"))
        app_row = Application(user_id=uid, job_id=job_id, cover_letter_id=letter_id, status=ApplicationStatus.SUBMITTED)
        s.add(app_row)
        await s.commit()
        app_id = app_row.id
    r = await client.put(f"/api/v1/applications/{app_id}/outcome", headers=auth_headers, json={"status": "hired"})
    assert r.status_code == 200
    [p] = await _proposals(uid)
    assert p.outcome == "hired" and p.was_hired is True
    assert p.facts_credited_at is not None
    assert await _times_in_won(fact_id) == 1

    if existing_row:
        r = await client.post("/api/v1/proposals/outcomes", headers=auth_headers,
                              json={"items": [{"upwork_proposal_id": "777", "status": "hired"}]})
        assert r.json()["credited"] == 0
        assert await _times_in_won(fact_id) == 1


@pytest.mark.asyncio
async def test_backfill_hired_credits_facts(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _uid(client, auth_headers)
    job_id, letter_id = await _seed_job_and_letter(uid)
    fact_id = await _seed_fact_on_letter(letter_id, uid)
    async with TestSessionLocal() as s:
        s.add(Application(user_id=uid, job_id=job_id, cover_letter_id=letter_id, status=ApplicationStatus.HIRED))
        await s.commit()
    r = await client.post("/api/v1/applications/backfill-proposals", headers=auth_headers)
    assert r.json()["created"] == 1
    [p] = await _proposals(uid)
    assert p.outcome == "hired" and p.facts_credited_at is not None
    assert await _times_in_won(fact_id) == 1
