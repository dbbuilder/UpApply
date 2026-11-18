"""POST /search-queries/evaluate: saved Upwork jobs are targets beside wins (Chris 2026-11-09), each
search is credited with the saved jobs it would have found, and query words match whole words."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.job import Job
from app.models.search_query import SearchQuery
from app.services.search_lab import job_matches_query, tokenize_query
from tests.conftest import TestSessionLocal

URL = "/api/v1/search-queries/evaluate"


def test_query_words_match_whole_words_only():
    assert job_matches_query("Senior AI engineer", "", tokenize_query("ai"))
    assert not job_matches_query("Maintain a WordPress site", "", tokenize_query("ai"))
    assert job_matches_query("Fractional CTO", "", tokenize_query("cto advisor"))
    assert job_matches_query("Build a .NET API", "", tokenize_query(".net"))
    assert job_matches_query("Node.js and C# backend", "", tokenize_query("c#"))


async def _seed(user_id: str):
    async with TestSessionLocal() as db:
        db.add_all([
            Job(user_id=user_id, upwork_url="https://u/~w1", title="Interim CTO for fintech",
                description="Lead the team", source="contract_import"),
            Job(user_id=user_id, upwork_url="https://u/~s1", title="Fractional CTO for SaaS",
                description="Own the roadmap", is_saved=True, source="saved"),
            Job(user_id=user_id, upwork_url="https://u/~s2", title="SQL Server performance rescue",
                description="Slow queries", is_saved=True, source="saved"),
            Job(user_id=user_id, upwork_url="https://u/~s3", title="Voice agent platform lead",
                description="Realtime speech", is_saved=True, source="saved"),
            Job(user_id=user_id, upwork_url="https://u/~x", title="Not saved, not won", description="d"),
            SearchQuery(user_id=user_id, query="fractional cto", active=True),
            SearchQuery(user_id=user_id, query="sql server", active=True),
            SearchQuery(user_id=user_id, query="wordpress", active=False),
        ])
        await db.commit()


@pytest.mark.asyncio
async def test_saved_jobs_are_targets_and_credit_the_searches(client: AsyncClient, auth_headers_with_profile):
    uid = (await client.get("/api/v1/auth/me", headers=auth_headers_with_profile)).json()["id"]
    await _seed(uid)
    gen = AsyncMock(return_value=[])
    with patch("app.api.v1.search_queries._generate_lab_suggestions", gen):
        resp = await client.post(URL, headers=auth_headers_with_profile)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_target_jobs"] == 4 and data["saved_target_jobs"] == 3
    by_query = {c["query"]: c for c in data["query_coverage"]}
    # "fractional cto" matches both CTO jobs (any word, as before); one of them is saved
    assert by_query["fractional cto"]["coverage_count"] == 2 and by_query["fractional cto"]["saved_count"] == 1
    assert by_query["sql server"]["coverage_count"] == 1 and by_query["sql server"]["saved_count"] == 1
    assert "wordpress" not in by_query  # inactive searches are not scored

    # The uncovered saved job is a gap, and the generator is asked to cover it
    assert data["gap_jobs"] == ["Voice agent platform lead"]
    assert gen.await_args.kwargs["gap_titles"] == ["Voice agent platform lead"]


@pytest.mark.asyncio
async def test_saved_jobs_alone_are_enough_to_evaluate(client: AsyncClient, auth_headers_with_profile):
    uid = (await client.get("/api/v1/auth/me", headers=auth_headers_with_profile)).json()["id"]
    async with TestSessionLocal() as db:
        db.add(Job(user_id=uid, upwork_url="https://u/~s1", title="Fractional CTO", description="d",
                   is_saved=True, source="saved"))
        await db.commit()
    with patch("app.api.v1.search_queries._generate_lab_suggestions", AsyncMock(return_value=[])):
        data = (await client.post(URL, headers=auth_headers_with_profile)).json()
    assert data["total_target_jobs"] == 1 and data["saved_target_jobs"] == 1
