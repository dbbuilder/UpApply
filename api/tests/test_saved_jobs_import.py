"""POST /jobs/import-bulk with source="saved": recent saves are analysed and shown in the Queue;
older ones (signal_only) are stored as a preference signal only (Chris 2026-11-09)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.job import Job
from tests.conftest import TestSessionLocal

URL = "/api/v1/jobs/import-bulk"


def _item(n: int, **kw) -> dict:
    item = {"upwork_job_id": f"0{n:018d}", "upwork_url": f"https://www.upwork.com/jobs/Job_~0{n:018d}/",
            "title": f"Fractional CTO {n}", "description": "Lead the platform", "posted_date_raw": "Posted 2 hours ago"}
    item.update(kw)
    return item


def _analysis():
    from app.services.job_analysis import AnalysisResult
    return AnalysisResult(match_score=77.0, skill_matches=[], missing_skills=[], strengths=[], concerns=[],
                          deal_breaker_warnings=[], relevant_memories=[], recommendation="Good")


async def _post(client, headers, body):
    analyse = AsyncMock(return_value=_analysis())
    with patch("app.api.v1.jobs.run_full_analysis", analyse), \
         patch("app.api.v1.jobs.generate_embedding", AsyncMock(return_value=[0.1] * 1536)):
        resp = await client.post(URL, headers=headers, json=body)
    return resp, analyse


async def _jobs(user_id):
    async with TestSessionLocal() as db:
        return {j.title: j for j in (await db.execute(select(Job).where(Job.user_id == user_id))).scalars()}


@pytest.mark.asyncio
async def test_old_saves_are_stored_as_signal_without_analysis(client: AsyncClient, auth_headers_with_profile):
    uid = (await client.get("/api/v1/auth/me", headers=auth_headers_with_profile)).json()["id"]
    body = {"source": "saved", "jobs": [_item(1), _item(2, signal_only=True, posted_date_raw="Posted 3 weeks ago")]}
    resp, analyse = await _post(client, auth_headers_with_profile, body)
    assert resp.status_code == 200
    jobs = await _jobs(uid)

    recent, old = jobs["Fractional CTO 1"], jobs["Fractional CTO 2"]
    assert recent.is_saved and recent.source == "saved" and float(recent.match_score) == 77.0
    assert old.is_saved and old.source == "saved_signal" and old.match_score is None
    assert old.embedding is not None  # the signal needs its embedding
    assert analyse.await_count == 1  # only the recent save was analysed
    # the analysis reuses the embedding instead of computing it again
    assert analyse.await_args.kwargs["precomputed_embedding"] is not None


@pytest.mark.asyncio
async def test_a_known_job_saved_later_becomes_a_saved_signal(client: AsyncClient, auth_headers_with_profile):
    uid = (await client.get("/api/v1/auth/me", headers=auth_headers_with_profile)).json()["id"]
    await _post(client, auth_headers_with_profile, {"source": "search", "jobs": [_item(3)]})
    assert not (await _jobs(uid))["Fractional CTO 3"].is_saved

    resp, analyse = await _post(client, auth_headers_with_profile, {"source": "saved", "jobs": [_item(3)]})
    assert resp.status_code == 200 and resp.json() == []  # nothing new created
    assert (await _jobs(uid))["Fractional CTO 3"].is_saved
    analyse.assert_not_awaited()


@pytest.mark.asyncio
async def test_job_list_can_leave_out_signal_only_saves(client: AsyncClient, auth_headers_with_profile):
    body = {"source": "saved", "jobs": [_item(4), _item(5, signal_only=True)]}
    await _post(client, auth_headers_with_profile, body)
    titles = lambda r: sorted(j["title"] for j in r.json())
    everything = await client.get("/api/v1/jobs", headers=auth_headers_with_profile)
    queue = await client.get("/api/v1/jobs?exclude_source=saved_signal", headers=auth_headers_with_profile)
    assert titles(everything) == ["Fractional CTO 4", "Fractional CTO 5"]
    assert titles(queue) == ["Fractional CTO 4"]
