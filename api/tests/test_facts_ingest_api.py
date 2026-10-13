"""Integration tests for fact ingestion endpoints (extraction + embeddings mocked)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.fact import Fact
from app.models.memory import Memory
from app.models.proposal import Proposal
from app.models.user import User
from app.schemas.fact import FactCandidate
from tests.conftest import TestSessionLocal
from tests.vector_utils import make_fake_embedder

BASE = "/api/v1/facts"


async def _fake_extract(text, source_type, source_ref=None, context=None):
    """Same statement for every item -> second item dedupes into the first."""
    return [FactCandidate(
        kind="metric", statement="Cut cloud spend 38% for a fintech client.", strength=0.8,
        source_type=source_type, source_ref=source_ref, source_snippet="cut spend 38%",
    )]


async def _per_ref_extract(text, source_type, source_ref=None, context=None):
    """Distinct statement per source_ref -> no dedupe."""
    return [FactCandidate(
        kind="project", statement=f"Fact from {source_ref}", strength=0.7,
        source_type=source_type, source_ref=source_ref,
    )]


@pytest.fixture
def fake_embed():
    mock = make_fake_embedder()
    with patch("app.services.facts.generate_embedding", mock):
        yield mock


async def _user_id(client, headers) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


@pytest.mark.asyncio
async def test_ingest_creates_merges_and_is_idempotent(client: AsyncClient, auth_headers: dict, fake_embed):
    extract = AsyncMock(side_effect=_fake_extract)
    payload = {
        "source_type": "chatgpt_user_turn",
        "items": [
            {"text": "We cut spend 38%", "source_ref": "conv-1", "context": "letter"},
            {"text": "Again: 38% cut", "source_ref": "conv-2"},
        ],
    }
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/ingest", headers=auth_headers, json=payload)
        assert r.status_code == 200
        assert r.json() == {"created": 1, "merged": 1, "auto_approved": 0, "skipped": 0, "failed": 0, "remaining": 0}

        r = await client.post(f"{BASE}/ingest", headers=auth_headers, json=payload)
        assert r.json()["skipped"] == 2
    assert extract.await_count == 2  # second run never re-extracts

    facts = (await client.get(BASE, headers=auth_headers, params={"status": "candidate"})).json()
    assert len(facts) == 1
    assert [s["source_ref"] for s in facts[0]["sources"]] == ["conv-1", "conv-2"]


@pytest.mark.asyncio
async def test_ingest_counts_extraction_failures(client: AsyncClient, auth_headers: dict, fake_embed):
    extract = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/ingest", headers=auth_headers, json={
            "source_type": "chatgpt_user_turn", "items": [{"text": "x", "source_ref": "c"}],
        })
    assert r.json()["failed"] == 1


@pytest.mark.asyncio
async def test_from_memories_uses_only_bio_memories_and_auto_approves(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        bio = Memory(user_id=uid, title="Stratavault.ai", content="Built Stratavault.ai", category="project", importance_score=1.0)
        s.add_all([
            bio,
            Memory(user_id=uid, title="Style", content="Prefers terse tone", category="lesson", importance_score=0.95),
            Memory(user_id=uid, title="Past Proposal", content="JOB POSTING:\nNeed dev", importance_score=0.9, exclude_from_retrieval=True),
            Memory(user_id=uid, title="Minor", content="Knows Excel", category="skill_demo", importance_score=0.5),
        ])
        await s.commit()
        bio_id = bio.id

    extract = AsyncMock(side_effect=_per_ref_extract)
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/from-memories", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["auto_approved"] == 1
    assert [c.args[2] for c in extract.await_args_list] == [bio_id]  # (text, source_type, source_ref, context)

    approved = (await client.get(BASE, headers=auth_headers, params={"status": "approved"})).json()
    assert [f["statement"] for f in approved] == [f"Fact from {bio_id}"]
    assert approved[0]["source_type"] == "bio_memory"


@pytest.mark.asyncio
async def test_from_proposals_marks_zero_fact_letters_and_retries_failures(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        s.add_all([
            Proposal(user_id=uid, cover_letter_text="Short thanks note", job_title="J1", source="scraped"),
            Proposal(user_id=uid, cover_letter_text="Letter that errors", job_title="J2", source="scraped"),
        ])
        await s.commit()

    async def _extract(text, source_type, source_ref=None, context=None):
        if "errors" in text:
            raise RuntimeError("haiku down")
        return []

    extract = AsyncMock(side_effect=_extract)
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers, params={"limit": 10})
        assert r.json()["failed"] == 1
        assert r.json()["remaining"] == 1  # the failed one only
        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers, params={"limit": 10})
    texts = [c.args[0] for c in extract.await_args_list]
    assert texts.count("Short thanks note") == 1  # zero-fact letter never re-extracted
    assert texts.count("Letter that errors") == 2  # failure retried


@pytest.mark.asyncio
async def test_from_proposals_batches_and_skips_ai_authored(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        s.add_all([
            Proposal(user_id=uid, cover_letter_text="Letter one", job_title="Job 1", job_text="Need SQL",
                     screening_answers=[{"question": "Experience?", "answer": "20 years"}], source="scraped"),
            Proposal(user_id=uid, cover_letter_text="Letter two", job_title="Job 2", source="scraped"),
            Proposal(user_id=uid, cover_letter_text="Letter three", job_title="Job 3", source="extension", author="chris_edited_ai"),
            Proposal(user_id=uid, cover_letter_text="ChatGPT letter", source="chatgpt_import", author="ai"),
            Proposal(user_id=uid, cover_letter_text="", job_title="Empty", source="scraped"),
        ])
        await s.commit()

    extract = AsyncMock(side_effect=_per_ref_extract)
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers, params={"limit": 2})
        assert r.json()["created"] == 2
        assert r.json()["remaining"] == 1

        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers, params={"limit": 2})
        assert r.json()["created"] == 1
        assert r.json()["remaining"] == 0

        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers, params={"limit": 2})
        assert r.json()["remaining"] == 0
    assert extract.await_count == 3  # nothing is re-extracted once processed

    texts = [c.args[0] for c in extract.await_args_list]
    assert len(texts) == 3
    assert not any("ChatGPT letter" in t for t in texts)
    assert any("Q: Experience?" in t and "A: 20 years" in t for t in texts)
    assert all(c.args[1] == "upwork_proposal" for c in extract.await_args_list)


@pytest.mark.asyncio
async def test_ingest_never_auto_approves_client_text(client: AsyncClient, auth_headers: dict, fake_embed):
    """Ingested text may quote clients/job posts; candidates always go to review (spec §1.7)."""
    extract = AsyncMock(side_effect=_per_ref_extract)
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/ingest", headers=auth_headers, json={
            "source_type": "chatgpt_user_turn", "auto_approve": True,
            "items": [{"text": "Built X", "source_ref": "conv-9"}],
        })
    assert r.json()["created"] == 1 and r.json()["auto_approved"] == 0
    approved = (await client.get(BASE, headers=auth_headers, params={"status": "approved"})).json()
    assert approved == []


@pytest.mark.asyncio
async def test_ingest_is_scoped_to_the_calling_user(client: AsyncClient, auth_headers: dict, fake_embed):
    """Another user's identical source_ref does not make this user's item skip."""
    async with TestSessionLocal() as s:
        other = User(email="other-ingest@example.com", hashed_password="x")
        s.add(other)
        await s.flush()
        s.add(Fact(user_id=other.id, kind="project", statement="Other", strength=0.5, status="candidate",
                   source_type="chatgpt_user_turn", source_ref="conv-1",
                   sources=[{"source_type": "chatgpt_user_turn", "source_ref": "conv-1", "snippet": None}]))
        await s.commit()
    extract = AsyncMock(side_effect=_per_ref_extract)
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/ingest", headers=auth_headers, json={
            "source_type": "chatgpt_user_turn", "items": [{"text": "Built X", "source_ref": "conv-1"}],
        })
    assert r.json()["skipped"] == 0 and r.json()["created"] == 1


@pytest.mark.asyncio
async def test_from_contracts_ingests_contract_jobs_once_as_candidates(client: AsyncClient, auth_headers: dict, fake_embed):
    from app.models.job import Job

    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        other = User(email="other-contracts@example.com", hashed_password="x")
        s.add(other)
        await s.flush()
        s.add_all([
            Job(user_id=uid, upwork_job_id="contract_1", upwork_url="https://www.upwork.com/nx/wm/workroom/1/overview",
                title="SQL Server tuning", description="SQL Server tuning\nRate: $95/hr\nClient: Acme Health",
                source="contract_import", is_saved=True),
            Job(user_id=uid, upwork_job_id="~01abc", upwork_url="https://www.upwork.com/jobs/~01abc",
                title="Not a contract", description="A job post", source="extension"),
            Job(user_id=other.id, upwork_job_id="contract_2", upwork_url="https://www.upwork.com/nx/wm/workroom/2/overview",
                title="Other user's contract", description="Other user's contract", source="contract_import"),
        ])
        await s.commit()

    extract = AsyncMock(side_effect=_per_ref_extract)
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/from-contracts", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["created"] == 1
        r = await client.post(f"{BASE}/from-contracts", headers=auth_headers)
        assert r.json()["created"] == 0
    assert [(c.args[1], c.args[2]) for c in extract.await_args_list] == [("upwork_contract", "contract_1")]
    assert "Acme Health" in extract.await_args_list[0].args[0]
    candidates = (await client.get(BASE, headers=auth_headers, params={"status": "candidate"})).json()
    assert [f["source_type"] for f in candidates] == ["upwork_contract"]


# --- Adversarial review regressions (phase 1) ---

async def _no_facts(text, source_type, source_ref=None, context=None):
    return []


@pytest.mark.asyncio
async def test_reopened_proposal_with_new_text_is_re_extracted(client: AsyncClient, auth_headers: dict, fake_embed):
    """import-from-upwork resets facts_ingested_at when the full letter arrives; the full text
    must be extracted even though a fact already cites this proposal."""
    from sqlalchemy import select

    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        p = Proposal(user_id=uid, cover_letter_text="Truncated letter", job_title="J", source="scraped")
        s.add(p)
        await s.commit()
        pid = p.id

    extract = AsyncMock(side_effect=_per_ref_extract)
    with patch("app.services.facts.extract_facts", extract):
        await client.post(f"{BASE}/from-proposals", headers=auth_headers)
        async with TestSessionLocal() as s:
            row = (await s.execute(select(Proposal).where(Proposal.id == pid))).scalar_one()
            row.cover_letter_text = "Truncated letter, now the full letter with answers"
            row.facts_ingested_at = None
            await s.commit()
        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers)
    assert r.json()["skipped"] == 0
    texts = [c.args[0] for c in extract.await_args_list]
    assert texts == ["Truncated letter", "Truncated letter, now the full letter with answers"]


@pytest.mark.asyncio
async def test_ingest_never_re_extracts_zero_fact_items(client: AsyncClient, auth_headers: dict, fake_embed):
    extract = AsyncMock(side_effect=_no_facts)
    payload = {"source_type": "chatgpt_user_turn", "items": [{"text": "Write me a job post", "source_ref": "conv-z"}]}
    with patch("app.services.facts.extract_facts", extract):
        await client.post(f"{BASE}/ingest", headers=auth_headers, json=payload)
        r = await client.post(f"{BASE}/ingest", headers=auth_headers, json=payload)
    assert r.json()["skipped"] == 1
    assert extract.await_count == 1


@pytest.mark.asyncio
async def test_from_contracts_marks_zero_fact_contracts_and_reports_remaining(client: AsyncClient, auth_headers: dict, fake_embed):
    from app.models.job import Job
    from app.services.facts import MAX_ITEMS_PER_RUN

    uid = await _user_id(client, auth_headers)
    n = MAX_ITEMS_PER_RUN + 5
    async with TestSessionLocal() as s:
        s.add_all([
            Job(user_id=uid, upwork_job_id=f"contract_{i}", upwork_url=f"https://www.upwork.com/nx/wm/workroom/{i}/overview",
                title=f"Contract {i}", description=f"Contract {i}", source="contract_import", is_saved=True)
            for i in range(n)
        ])
        await s.commit()

    extract = AsyncMock(side_effect=_no_facts)
    with patch("app.services.facts.extract_facts", extract):
        r1 = (await client.post(f"{BASE}/from-contracts", headers=auth_headers)).json()
        r2 = (await client.post(f"{BASE}/from-contracts", headers=auth_headers)).json()
        r3 = (await client.post(f"{BASE}/from-contracts", headers=auth_headers)).json()
    assert r1["remaining"] == 5
    assert r2["remaining"] == 0
    assert r3["skipped"] == n and r3["remaining"] == 0
    assert extract.await_count == n  # each contract extracted exactly once
    assert len({c.args[2] for c in extract.await_args_list}) == n


@pytest.mark.asyncio
async def test_from_memories_caps_batch_and_reports_remaining(client: AsyncClient, auth_headers: dict, fake_embed):
    from app.services.facts import MAX_ITEMS_PER_RUN

    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        s.add_all([
            Memory(user_id=uid, title=f"Bio {i}", content=f"Built thing {i}", category="project", importance_score=0.95)
            for i in range(MAX_ITEMS_PER_RUN + 3)
        ])
        await s.commit()

    extract = AsyncMock(side_effect=_no_facts)
    with patch("app.services.facts.extract_facts", extract):
        r = (await client.post(f"{BASE}/from-memories", headers=auth_headers)).json()
        assert extract.await_count == MAX_ITEMS_PER_RUN
        assert r["remaining"] == 3
        r = (await client.post(f"{BASE}/from-memories", headers=auth_headers)).json()
    assert extract.await_count == MAX_ITEMS_PER_RUN + 3
    assert r["remaining"] == 0


@pytest.mark.asyncio
async def test_from_proposals_gives_up_on_persistent_failures(client: AsyncClient, auth_headers: dict, fake_embed):
    from app.services.facts import MAX_EXTRACTION_ATTEMPTS

    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        s.add(Proposal(user_id=uid, cover_letter_text="Always truncates", job_title="J", source="scraped"))
        await s.commit()

    extract = AsyncMock(side_effect=RuntimeError("max_tokens"))
    remaining = []
    with patch("app.services.facts.extract_facts", extract):
        for _ in range(MAX_EXTRACTION_ATTEMPTS + 1):
            remaining.append((await client.post(f"{BASE}/from-proposals", headers=auth_headers)).json()["remaining"])
    assert remaining == [1] * (MAX_EXTRACTION_ATTEMPTS - 1) + [0, 0]
    assert extract.await_count == MAX_EXTRACTION_ATTEMPTS


@pytest.mark.asyncio
async def test_ingest_bounds_concurrent_extractions(client: AsyncClient, auth_headers: dict, fake_embed):
    import asyncio

    from app.services.facts import MAX_CONCURRENT_EXTRACTIONS

    state = {"now": 0, "peak": 0}

    async def _slow(text, source_type, source_ref=None, context=None):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return []

    items = [{"text": f"t{i}", "source_ref": f"c{i}"} for i in range(25)]
    with patch("app.services.facts.extract_facts", AsyncMock(side_effect=_slow)):
        r = await client.post(f"{BASE}/ingest", headers=auth_headers, json={"source_type": "chatgpt_user_turn", "items": items})
    assert r.status_code == 200
    assert 1 < state["peak"] <= MAX_CONCURRENT_EXTRACTIONS


def test_fact_llm_endpoints_are_rate_limited():
    from app.core.rate_limit import limiter

    for name in ("ingest_facts", "facts_from_memories", "facts_from_proposals", "facts_from_contracts"):
        assert f"app.api.v1.facts.{name}" in limiter._route_limits, name
