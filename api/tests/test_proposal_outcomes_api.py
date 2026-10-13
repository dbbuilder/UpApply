"""API tests for POST /api/v1/proposals/outcomes (real DB, real credit_facts)."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.cover_letter import CoverLetter
from app.models.fact import Fact
from app.models.job import Job
from app.models.proposal import Proposal
from tests.conftest import TestSessionLocal

URL = "/api/v1/proposals/outcomes"


async def _uid(client: AsyncClient, headers: dict) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


async def _seed(user_id: str, *, upwork_id: str | None, title: str, days_ago: int = 2,
                with_fact: bool = True) -> dict:
    async with TestSessionLocal() as s:
        job = Job(user_id=user_id, upwork_url=f"https://www.upwork.com/jobs/~{title[:4]}",
                  title=title, description="desc", skills_required=[])
        s.add(job)
        await s.flush()
        fact_ids = []
        if with_fact:
            fact = Fact(user_id=user_id, kind="project", statement=f"Fact for {title}", detail=None,
                        skills=[], industries=[], job_types=["cloud"], strength=0.8,
                        status="approved", source_type="bio_memory", sources=[],
                        times_used=1, times_in_won=0, embedding=[0.1] * 1536)
            s.add(fact)
            await s.flush()
            fact_ids = [fact.id]
        s.add(CoverLetter(user_id=user_id, job_id=job.id, content="draft", model_used="m",
                          fact_ids_used=fact_ids, final_text="final"))
        prop = Proposal(user_id=user_id, job_id=job.id, upwork_proposal_id=upwork_id,
                        cover_letter_text="final", job_title=title, source="extension",
                        author="chris_edited_ai",
                        submitted_at=datetime.now(timezone.utc) - timedelta(days=days_ago))
        s.add(prop)
        await s.commit()
        return {"proposal_id": prop.id, "fact_id": fact_ids[0] if fact_ids else None}


def _upwork_date(days_ago: int) -> str:
    d = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return f"{d:%b} {d.day}, {d.year}"  # Upwork list format, e.g. "Mar 3, 2026"


async def _prop(pid: str) -> Proposal:
    async with TestSessionLocal() as s:
        return (await s.execute(select(Proposal).where(Proposal.id == pid))).scalar_one()


async def _times_in_won(fid) -> int:
    async with TestSessionLocal() as s:
        return (await s.execute(select(Fact.times_in_won).where(Fact.id == fid))).scalar_one()


@pytest.mark.asyncio
async def test_reply_credits_facts_once(client, auth_headers):
    uid = await _uid(client, auth_headers)
    seeded = await _seed(uid, upwork_id="111", title="Azure SQL migration lead")

    r = await client.post(URL, headers=auth_headers,
                          json={"items": [{"upwork_proposal_id": "111", "status": "responded"}]})
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 1, "credited": 1, "not_found": 0}
    prop = await _prop(seeded["proposal_id"])
    assert prop.outcome == "replied" and prop.client_responded is True
    assert await _times_in_won(seeded["fact_id"]) == 1

    # Same status again: no change, no double credit. Upgrade to hired: outcome moves, still no double credit.
    r = await client.post(URL, headers=auth_headers,
                          json={"items": [{"upwork_proposal_id": "111", "status": "responded"}]})
    assert r.json() == {"updated": 0, "credited": 0, "not_found": 0}
    r = await client.post(URL, headers=auth_headers,
                          json={"items": [{"upwork_proposal_id": "111", "status": "hired"}]})
    assert r.json() == {"updated": 1, "credited": 0, "not_found": 0}
    prop = await _prop(seeded["proposal_id"])
    assert prop.outcome == "hired" and prop.was_hired is True
    assert await _times_in_won(seeded["fact_id"]) == 1


@pytest.mark.asyncio
async def test_title_fallback_stamps_upwork_id(client, auth_headers):
    uid = await _uid(client, auth_headers)
    seeded = await _seed(uid, upwork_id=None, title="Build a Next.js dashboard")
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"upwork_proposal_id": "222", "job_title": "Build a Next.js dashboard", "status": "interviewed",
         "submitted_at": _upwork_date(2)},
    ]})
    assert r.json() == {"updated": 1, "credited": 1, "not_found": 0}
    prop = await _prop(seeded["proposal_id"])
    assert prop.upwork_proposal_id == "222" and prop.outcome == "interviewed"


@pytest.mark.asyncio
async def test_stale_submitted_becomes_no_response_without_credit(client, auth_headers):
    uid = await _uid(client, auth_headers)
    stale = await _seed(uid, upwork_id="333", title="Old job", days_ago=20)
    fresh = await _seed(uid, upwork_id="444", title="New job", days_ago=3)
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"upwork_proposal_id": "333", "status": "submitted"},
        {"upwork_proposal_id": "444", "status": "submitted"},
        {"upwork_proposal_id": "999", "status": "responded"},
    ]})
    assert r.json() == {"updated": 1, "credited": 0, "not_found": 1}
    assert (await _prop(stale["proposal_id"])).outcome == "no_response"
    assert (await _prop(fresh["proposal_id"])).outcome is None
    assert await _times_in_won(stale["fact_id"]) == 0


@pytest.mark.asyncio
async def test_by_internal_id_and_other_users_isolated(client, auth_headers):
    uid = await _uid(client, auth_headers)
    seeded = await _seed(uid, upwork_id=None, title="Direct id", with_fact=False)
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"proposal_id": seeded["proposal_id"], "status": "viewed"},
    ]})
    assert r.json() == {"updated": 1, "credited": 0, "not_found": 0}

    other = await client.post("/api/v1/auth/register",
                              json={"email": "other@example.com", "password": "testpass123"})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    r = await client.post(URL, headers=other_headers, json={"items": [
        {"proposal_id": seeded["proposal_id"], "status": "hired"},
    ]})
    assert r.json() == {"updated": 0, "credited": 0, "not_found": 1}
    assert (await _prop(seeded["proposal_id"])).outcome == "viewed"


@pytest.mark.asyncio
async def test_requires_auth(client):
    r = await client.post(URL, json={"items": []})
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_detail_import_links_click_capture_and_credits_once(client, auth_headers):
    from unittest.mock import AsyncMock, patch

    uid = await _uid(client, auth_headers)
    seeded = await _seed(uid, upwork_id=None, title="Fabric data platform build")
    payload = {"proposals": [{
        "proposalId": "999", "jobTitle": "Fabric data platform build",
        "coverLetter": "final", "status": "Interviewing", "outcome": "interviewed",
        "submittedAt": _upwork_date(2),
    }]}
    with patch("app.api.v1.proposals.generate_embedding", AsyncMock(return_value=[0.1] * 1536)):
        r = await client.post("/api/v1/proposals/import-from-upwork", headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        r = await client.post("/api/v1/proposals/import-from-upwork", headers=auth_headers, json=payload)
    async with TestSessionLocal() as s:
        rows = (await s.execute(select(Proposal).where(Proposal.user_id == uid))).scalars().all()
    assert [p.id for p in rows] == [seeded["proposal_id"]]  # no duplicate voice sample
    assert rows[0].upwork_proposal_id == "999"
    assert rows[0].outcome == "interviewed"
    assert await _times_in_won(seeded["fact_id"]) == 1  # second import does not re-credit


@pytest.mark.asyncio
async def test_rejects_more_than_500_items(client, auth_headers):
    items = [{"upwork_proposal_id": str(i), "status": "viewed"} for i in range(501)]
    r = await client.post(URL, headers=auth_headers, json={"items": items})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_title_fallback_ignores_same_title_proposal_from_another_day(client, auth_headers):
    """A direct-on-Upwork proposal with a generic title must not bind to a click-captured row."""
    uid = await _uid(client, auth_headers)
    captured = await _seed(uid, upwork_id=None, title="React Developer", days_ago=1)
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"upwork_proposal_id": "A", "job_title": "React Developer", "status": "hired",
         "submitted_at": _upwork_date(30)},
        {"upwork_proposal_id": "B", "job_title": "React Developer", "status": "submitted",
         "submitted_at": _upwork_date(1)},
    ]})
    assert r.json() == {"updated": 0, "credited": 0, "not_found": 1}
    prop = await _prop(captured["proposal_id"])
    assert prop.upwork_proposal_id == "B" and prop.outcome is None and prop.was_hired is not True
    assert await _times_in_won(captured["fact_id"]) == 0


@pytest.mark.asyncio
async def test_title_fallback_needs_a_submitted_date(client, auth_headers):
    uid = await _uid(client, auth_headers)
    captured = await _seed(uid, upwork_id=None, title="Full Stack Developer")
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"upwork_proposal_id": "A", "job_title": "Full Stack Developer", "status": "hired"},
    ]})
    assert r.json() == {"updated": 0, "credited": 0, "not_found": 1}
    assert (await _prop(captured["proposal_id"])).upwork_proposal_id is None


@pytest.mark.asyncio
async def test_title_fallback_skips_ambiguous_same_day_items(client, auth_headers):
    """Two same-title, same-day Upwork rows: neither can be told apart, so neither binds."""
    uid = await _uid(client, auth_headers)
    captured = await _seed(uid, upwork_id=None, title="Full Stack Developer")
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"upwork_proposal_id": "A", "job_title": "Full Stack Developer", "status": "hired",
         "submitted_at": _upwork_date(2)},
        {"upwork_proposal_id": "B", "job_title": "Full Stack Developer", "status": "submitted",
         "submitted_at": _upwork_date(2)},
    ]})
    assert r.json() == {"updated": 0, "credited": 0, "not_found": 2}
    prop = await _prop(captured["proposal_id"])
    assert prop.upwork_proposal_id is None and prop.outcome is None
    assert await _times_in_won(captured["fact_id"]) == 0


@pytest.mark.asyncio
async def test_detail_import_does_not_overwrite_same_title_row_from_another_day(client, auth_headers):
    from unittest.mock import AsyncMock, patch

    uid = await _uid(client, auth_headers)
    captured = await _seed(uid, upwork_id=None, title="React Developer", days_ago=1)
    payload = {"proposals": [{
        "proposalId": "OLD", "jobTitle": "React Developer", "coverLetter": "A much longer old letter " * 5,
        "status": "Hired", "outcome": "hired", "submittedAt": _upwork_date(40),
    }]}
    with patch("app.api.v1.proposals.generate_embedding", AsyncMock(return_value=[0.1] * 1536)):
        r = await client.post("/api/v1/proposals/import-from-upwork", headers=auth_headers, json=payload)
    assert r.status_code == 200, r.text
    prop = await _prop(captured["proposal_id"])
    assert prop.upwork_proposal_id is None and prop.cover_letter_text == "final" and prop.outcome is None
    assert await _times_in_won(captured["fact_id"]) == 0


@pytest.mark.asyncio
async def test_title_fallback_never_binds_a_row_with_another_upwork_id(client, auth_headers):
    """Same title and day, but the row is already bound to a different Upwork proposal."""
    uid = await _uid(client, auth_headers)
    bound = await _seed(uid, upwork_id="BOUND", title="Data Engineer", days_ago=2)
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"upwork_proposal_id": "OTHER", "job_title": "Data Engineer", "status": "hired",
         "submitted_at": _upwork_date(2)},
    ]})
    assert r.json() == {"updated": 0, "credited": 0, "not_found": 1}
    prop = await _prop(bound["proposal_id"])
    assert prop.upwork_proposal_id == "BOUND" and prop.outcome is None
    assert await _times_in_won(bound["fact_id"]) == 0


@pytest.mark.asyncio
async def test_title_bind_in_a_batch_is_not_reused_by_a_later_item(client, auth_headers):
    """Two items on adjacent days both fall in one row's ±1 day window: the first binds it,
    and the second (now a different Upwork id) must neither overwrite nor credit it."""
    uid = await _uid(client, auth_headers)
    captured = await _seed(uid, upwork_id=None, title="ETL Pipeline", days_ago=2)
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"upwork_proposal_id": "A", "job_title": "ETL Pipeline", "status": "submitted",
         "submitted_at": _upwork_date(2)},
        {"upwork_proposal_id": "B", "job_title": "ETL Pipeline", "status": "hired",
         "submitted_at": _upwork_date(3)},
    ]})
    assert r.json() == {"updated": 0, "credited": 0, "not_found": 1}
    prop = await _prop(captured["proposal_id"])
    assert prop.upwork_proposal_id == "A" and prop.outcome is None and prop.was_hired is not True
    assert await _times_in_won(captured["fact_id"]) == 0
