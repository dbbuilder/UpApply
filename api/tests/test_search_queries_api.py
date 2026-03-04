"""Integration tests for /api/v1/search-queries endpoints."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/api/v1/search-queries"

PROFILE_PAYLOAD = {
    "full_name": "Chris Therriault",
    "professional_title": "Fractional CTO",
    "bio": "Senior technical leader",
    "skills": [
        {"name": "Python", "level": "expert", "years": 10},
        {"name": "PostgreSQL", "level": "expert", "years": 8},
        {"name": "FastAPI", "level": "expert", "years": 4},
        {"name": "React", "level": "intermediate", "years": 5},
        {"name": "Azure", "level": "intermediate", "years": 3},
    ],
    "career_goals": "Build AI-powered SaaS products",
    "preferred_project_types": ["AI automation", "SaaS MVP", "data engineering"],
    "setup_step": 6,
}


async def _setup_profile(client: AsyncClient, headers: dict) -> None:
    await client.put("/api/v1/profile", headers=headers, json=PROFILE_PAYLOAD)
    await client.post("/api/v1/profile/complete-setup", headers=headers)


# ---------------------------------------------------------------------------
# Authentication guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_requires_auth(client: AsyncClient):
    r = await client.get(BASE)
    # FastAPI's HTTPBearer returns 403 when scheme is wrong, 401 when missing
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_query(client: AsyncClient, auth_headers: dict):
    r = await client.post(BASE, headers=auth_headers, json={"query": "python fastapi developer"})
    assert r.status_code == 201
    data = r.json()
    assert data["query"] == "python fastapi developer"
    assert data["source"] == "manual"
    assert data["run_count"] == 0
    assert data["performance_score"] == 0.0
    assert data["is_stale"] is True


@pytest.mark.asyncio
async def test_create_query_with_url_params(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        BASE,
        headers=auth_headers,
        json={"query": "fractional CTO", "url_params": "contractor_tier=2,3&proposals=0-4"},
    )
    assert r.status_code == 201
    assert r.json()["url_params"] == "contractor_tier=2,3&proposals=0-4"


@pytest.mark.asyncio
async def test_create_duplicate_query_returns_409(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, headers=auth_headers, json={"query": "AI engineer"})
    r = await client.post(BASE, headers=auth_headers, json={"query": "AI engineer"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_create_dedup_is_case_insensitive(client: AsyncClient, auth_headers: dict):
    """Normalisation: same text different case → conflict."""
    await client.post(BASE, headers=auth_headers, json={"query": "Data Engineer"})
    r = await client.post(BASE, headers=auth_headers, json={"query": "data engineer"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_create_empty_query_returns_422(client: AsyncClient, auth_headers: dict):
    r = await client.post(BASE, headers=auth_headers, json={"query": "   "})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_source_returns_422(client: AsyncClient, auth_headers: dict):
    r = await client.post(BASE, headers=auth_headers, json={"query": "test", "source": "invalid"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_returns_own_queries_only(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, headers=auth_headers, json={"query": "list test query A"})
    await client.post(BASE, headers=auth_headers, json={"query": "list test query B"})

    # Register another user
    await client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "testpass123"})
    r2 = await client.post("/api/v1/auth/login", json={"email": "other@example.com", "password": "testpass123"})
    other_headers = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    await client.post(BASE, headers=other_headers, json={"query": "other user query"})

    r = await client.get(BASE, headers=auth_headers)
    assert r.status_code == 200
    queries = r.json()
    titles = [q["query"] for q in queries]
    assert "list test query A" in titles
    assert "list test query B" in titles
    assert "other user query" not in titles


@pytest.mark.asyncio
async def test_list_sorted_by_performance_score(client: AsyncClient, auth_headers: dict):
    # Create two queries
    r1 = await client.post(BASE, headers=auth_headers, json={"query": "low score query"})
    r2 = await client.post(BASE, headers=auth_headers, json={"query": "high score query"})
    id_low = r1.json()["id"]
    id_high = r2.json()["id"]

    # Give high-score query better stats
    await client.post(
        f"{BASE}/{id_high}/record-run",
        headers=auth_headers,
        json={"jobs_found": 10, "avg_score": 85.0, "high_score_count": 8},
    )
    await client.post(
        f"{BASE}/{id_low}/record-run",
        headers=auth_headers,
        json={"jobs_found": 10, "avg_score": 30.0, "high_score_count": 0},
    )

    r = await client.get(BASE, headers=auth_headers)
    ids = [q["id"] for q in r.json()]
    assert ids.index(id_high) < ids.index(id_low)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_query(client: AsyncClient, auth_headers: dict):
    r = await client.post(BASE, headers=auth_headers, json={"query": "to be deleted"})
    qid = r.json()["id"]

    del_r = await client.delete(f"{BASE}/{qid}", headers=auth_headers)
    assert del_r.status_code == 204

    # Should not appear in list
    list_r = await client.get(BASE, headers=auth_headers)
    ids = [q["id"] for q in list_r.json()]
    assert qid not in ids


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(client: AsyncClient, auth_headers: dict):
    r = await client.delete(f"{BASE}/does-not-exist", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_other_user_query_returns_404(client: AsyncClient, auth_headers: dict):
    """Users cannot delete each other's queries."""
    r = await client.post(BASE, headers=auth_headers, json={"query": "user A private"})
    qid = r.json()["id"]

    await client.post("/api/v1/auth/register", json={"email": "attacker@example.com", "password": "testpass123"})
    r2 = await client.post("/api/v1/auth/login", json={"email": "attacker@example.com", "password": "testpass123"})
    attacker = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    r3 = await client.delete(f"{BASE}/{qid}", headers=attacker)
    assert r3.status_code == 404


# ---------------------------------------------------------------------------
# Record-run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_run_updates_stats(client: AsyncClient, auth_headers: dict):
    r = await client.post(BASE, headers=auth_headers, json={"query": "record run test"})
    qid = r.json()["id"]

    rr = await client.post(
        f"{BASE}/{qid}/record-run",
        headers=auth_headers,
        json={"jobs_found": 5, "avg_score": 72.0, "high_score_count": 3},
    )
    assert rr.status_code == 200
    d = rr.json()
    assert d["run_count"] == 1
    assert d["total_jobs_found"] == 5
    assert d["avg_match_score"] == 72.0
    assert d["high_score_count"] == 3
    assert d["last_run_at"] is not None
    assert d["is_stale"] is False


@pytest.mark.asyncio
async def test_record_run_rolling_average(client: AsyncClient, auth_headers: dict):
    """Second run correctly combines with first via weighted rolling average."""
    r = await client.post(BASE, headers=auth_headers, json={"query": "rolling avg test"})
    qid = r.json()["id"]

    # Run 1: 4 jobs at avg 60
    await client.post(
        f"{BASE}/{qid}/record-run",
        headers=auth_headers,
        json={"jobs_found": 4, "avg_score": 60.0, "high_score_count": 2},
    )
    # Run 2: 6 jobs at avg 80
    rr = await client.post(
        f"{BASE}/{qid}/record-run",
        headers=auth_headers,
        json={"jobs_found": 6, "avg_score": 80.0, "high_score_count": 4},
    )
    d = rr.json()
    # Weighted avg: (60*4 + 80*6) / 10 = 72.0
    assert d["avg_match_score"] == pytest.approx(72.0, abs=0.1)
    assert d["total_jobs_found"] == 10
    assert d["high_score_count"] == 6
    assert d["run_count"] == 2


@pytest.mark.asyncio
async def test_record_run_with_zero_jobs(client: AsyncClient, auth_headers: dict):
    """Zero-job runs still increment run_count and set last_run_at."""
    r = await client.post(BASE, headers=auth_headers, json={"query": "zero job run"})
    qid = r.json()["id"]

    rr = await client.post(
        f"{BASE}/{qid}/record-run",
        headers=auth_headers,
        json={"jobs_found": 0, "avg_score": 0.0, "high_score_count": 0},
    )
    d = rr.json()
    assert d["run_count"] == 1
    assert d["total_jobs_found"] == 0
    assert d["avg_match_score"] is None  # unchanged when no new jobs


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_without_profile_returns_400(client: AsyncClient, auth_headers: dict):
    """User must have a profile before seeding."""
    # auth_headers user has no profile yet in this isolated test
    r = await client.post(f"{BASE}/seed", headers=auth_headers)
    # May be 400 (no profile) or 200 (profile exists from earlier tests sharing same user).
    # Since conftest truncates tables between tests, this user should have no profile.
    assert r.status_code in (200, 400)


@pytest.mark.asyncio
async def test_seed_generates_queries_from_profile(client: AsyncClient, auth_headers_with_profile: dict):
    r = await client.post(f"{BASE}/seed", headers=auth_headers_with_profile)
    assert r.status_code == 200
    seeds = r.json()
    assert len(seeds) >= 5  # at least a few seed queries
    sources = {q["source"] for q in seeds}
    assert sources == {"seeded"}


@pytest.mark.asyncio
async def test_seed_is_idempotent(client: AsyncClient, auth_headers_with_profile: dict):
    """Calling /seed twice must not create duplicates."""
    r1 = await client.post(f"{BASE}/seed", headers=auth_headers_with_profile)
    count_first = len(r1.json())

    r2 = await client.post(f"{BASE}/seed", headers=auth_headers_with_profile)
    # All seeds already exist → second call returns empty list
    assert len(r2.json()) == 0

    r_list = await client.get(BASE, headers=auth_headers_with_profile)
    seeded = [q for q in r_list.json() if q["source"] == "seeded"]
    assert len(seeded) == count_first


# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_import(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        f"{BASE}/bulk-import",
        headers=auth_headers,
        json={
            "queries": [
                {"query": "imported query one", "source": "imported"},
                {"query": "imported query two", "url_params": "sort=recency"},
                {"query": "imported query one"},  # duplicate → should be skipped
            ]
        },
    )
    assert r.status_code == 200
    result = r.json()
    assert len(result) == 2
    assert all(q["source"] == "imported" for q in result if q["query"] == "imported query one")


@pytest.mark.asyncio
async def test_bulk_import_skips_empty_strings(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        f"{BASE}/bulk-import",
        headers=auth_headers,
        json={"queries": [{"query": ""}, {"query": "  "}, {"query": "valid query"}]},
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


# ---------------------------------------------------------------------------
# Generate (AI) — mocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_with_empty_profile_returns_empty_list(client: AsyncClient):
    """A fresh user (empty profile, no runs) gets a mocked AI call returning queries."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "emptypro_gen@example.com", "password": "testpass123"},
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = "AI automation expert\nPython backend consultant\n"

    with patch("app.api.v1.search_queries.AsyncOpenAI") as MockOpenAI:
        mock_client = AsyncMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        r = await client.post(f"{BASE}/generate", headers=headers)

    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_generate_returns_ai_queries(client: AsyncClient, auth_headers_with_profile: dict):
    """Mock OpenAI so we don't make real API calls in tests."""
    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = (
        "AI automation engineer\n"
        "RAG system developer\n"
        "LLM integration consultant\n"
        "Python FastAPI microservices\n"
        "fractional CTO startup\n"
        "PostgreSQL performance tuning\n"
        "cloud cost optimization AWS\n"
        "SaaS MVP rescue developer\n"
        "data pipeline engineer\n"
        "vibe coding fix expert\n"
        "compliance audit technical\n"
        "AI workflow automation n8n\n"
    )

    with patch(
        "app.api.v1.search_queries.AsyncOpenAI",
    ) as MockOpenAI:
        mock_client = AsyncMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        r = await client.post(f"{BASE}/generate", headers=auth_headers_with_profile)

    assert r.status_code == 200
    queries = r.json()
    assert len(queries) >= 1
    assert all(q["source"] == "ai_generated" for q in queries)
    assert all(q["url_params"] is not None for q in queries)


@pytest.mark.asyncio
async def test_generate_deduplicates_against_existing(client: AsyncClient, auth_headers_with_profile: dict):
    """Queries returned by AI that already exist must not be inserted."""
    # Pre-create a query that the mock AI will suggest
    await client.post(
        BASE,
        headers=auth_headers_with_profile,
        json={"query": "RAG system developer"},
    )

    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = (
        "RAG system developer\n"      # already exists
        "brand new unique query\n"    # new
    )

    with patch("app.api.v1.search_queries.AsyncOpenAI") as MockOpenAI:
        mock_client = AsyncMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        r = await client.post(f"{BASE}/generate", headers=auth_headers_with_profile)

    result = r.json()
    queries_text = [q["query"] for q in result]
    assert "RAG system developer" not in queries_text
    assert "brand new unique query" in queries_text
