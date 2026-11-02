"""POST /api/v1/job-queue/ingest: dedupe, pre-filter, scoring cap, threshold, statuses, query stats."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.models.job import Job
from app.models.job_queue import JobQueueItem
from app.models.outcome_event import OutcomeEvent
from app.models.search_query import SearchQuery
from app.models.user import User, UserProfile
from app.models.user_autonomy_profile import UserAutonomyProfile
from app.services.job_ingest import derive_chips, parse_posted_at, upwork_job_slug
from tests.conftest import TestSessionLocal

URL = "/api/v1/job-queue/ingest"


def _job(n: int, **kw) -> dict:
    job = {
        "upwork_url": f"https://www.upwork.com/jobs/Build-API_~01aa{n:014d}/",
        "title": f"FastAPI backend {n}",
        "description": "Python API with PostgreSQL.",
        "skills": ["Python", "PostgreSQL"],
        "budget_amount": "$2,000",
        "budget_type": "fixed",
    }
    job.update(kw)
    return job


def _analysis(score: float = 80.0):
    return SimpleNamespace(match_score=score, reason="Strong Python fit", strengths=["Deep Python"],
                           missing_skills=["Rust"], skill_matches=[], relevant_memories=[])


def _scorer(*scores):
    """run_full_analysis stand-in returning the given scores in order (last one repeats)."""
    seq = list(scores) or [80.0]

    async def fake(**kwargs):
        fake.calls.append(kwargs)
        return _analysis(seq[min(len(fake.calls) - 1, len(seq) - 1)])

    fake.calls = []
    return fake


async def _post(client, headers, body, scorer=None):
    scorer = scorer or _scorer()
    with patch("app.services.job_analysis.run_full_analysis", scorer):
        return await client.post(URL, headers=headers, json=body)


async def _user_id(client, headers) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


async def _items(user_id):
    async with TestSessionLocal() as db:
        return (await db.execute(select(JobQueueItem).where(JobQueueItem.user_id == user_id)
                                 .order_by(JobQueueItem.title))).scalars().all()


async def _set_profile(user_id, **values):
    async with TestSessionLocal() as db:
        await db.execute(update(UserProfile).where(UserProfile.user_id == user_id).values(**values))
        await db.commit()


# ── auth, validation ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient):
    r = await client.post(URL, json={"jobs": []})
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_validation(client: AsyncClient, auth_headers_with_profile):
    h = auth_headers_with_profile
    assert (await _post(client, h, {"jobs": [_job(i) for i in range(26)]})).status_code == 422
    assert (await _post(client, h, {"jobs": [_job(1, title="x" * 301)]})).status_code == 422
    assert (await _post(client, h, {"jobs": [_job(1, description="x" * 20001)]})).status_code == 422
    assert (await _post(client, h, {"jobs": [_job(1, skills=["s"] * 51)]})).status_code == 422
    assert (await _post(client, h, {"jobs": [_job(1, budget_type="weekly")]})).status_code == 422
    assert (await _post(client, h, {"jobs": [_job(1, upwork_url="https://evil.example/jobs/~01ab")]})).status_code == 422
    assert (await _post(client, h, {"jobs": [_job(1, upwork_url="javascript:alert(1)//upwork.com")]})).status_code == 422
    assert (await _post(client, h, {"jobs": [{"title": "no url"}]})).status_code == 422


@pytest.mark.asyncio
async def test_response_shape_and_minimal_job(client: AsyncClient, auth_headers_with_profile):
    body = {"query_id": None, "query": None, "jobs": [{
        "upwork_url": "https://www.upwork.com/jobs/~01minimal000000001", "title": "FastAPI work",
        "description": None, "client_info": {"rating": 4.9, "jobs_posted": 12, "hire_rate": "80%",
                                             "payment_verified": True, "unknown_key": "dropped"},
        "proposals_text": "5 to 10", "posted_at": "not a date",
    }]}
    r = await _post(client, auth_headers_with_profile, body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data) == {"received", "duplicates", "pre_filtered", "scored", "suggested",
                         "below_threshold", "queued_ids"}
    assert data["received"] == 1 and data["suggested"] == 1 and len(data["queued_ids"]) == 1
    item = (await _items(await _user_id(client, auth_headers_with_profile)))[0]
    assert item.client_info == {"rating": "4.9", "jobs_posted": "12", "hire_rate": "80%",
                                "payment_verified": True, "proposals": "5 to 10"}
    assert item.description == ""


# ── dedupe ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dedupe_against_queue_jobs_and_batch(client: AsyncClient, auth_headers_with_profile):
    h = auth_headers_with_profile
    uid = await _user_id(client, h)
    async with TestSessionLocal() as db:
        db.add(JobQueueItem(user_id=uid, upwork_url="https://www.upwork.com/jobs/Old-title_~01aa00000000000001/",
                            title="queued already"))
        db.add(Job(user_id=uid, upwork_url="https://www.upwork.com/freelance-jobs/apply/x_~01aa00000000000002/",
                   title="seen in jobs", description="d"))
        db.add(Job(user_id=uid, upwork_url="https://www.upwork.com/some/other/path", upwork_job_id="~01aa00000000000003",
                   title="job id only", description="d"))
        db.add(Job(user_id=uid, upwork_url="https://www.upwork.com/jobs/no-slug-here", title="no slug", description="d"))
        await db.commit()

    jobs = [
        _job(1),                                                     # same slug as the queue item, other URL
        _job(2),                                                     # same slug as a jobs row
        _job(3),                                                     # matches jobs.upwork_job_id
        _job(4, upwork_url="https://www.upwork.com/jobs/no-slug-here"),  # exact URL fallback
        _job(5),                                                     # new
        _job(5, upwork_url="https://www.upwork.com/jobs/Renamed_~01aa00000000000005?source=rss"),  # in-batch slug
        _job(6, upwork_url="https://www.upwork.com/jobs/plain"),     # new, no slug
        _job(7, upwork_url="https://www.upwork.com/jobs/plain"),     # in-batch exact URL
    ]
    scorer = _scorer()
    r = await _post(client, h, {"jobs": jobs}, scorer)
    data = r.json()
    assert data["received"] == 8 and data["duplicates"] == 6 and data["scored"] == 2, data
    assert len(scorer.calls) == 2
    titles = sorted(i.title for i in await _items(uid))
    assert "FastAPI backend 5" in titles and "FastAPI backend 6" in titles and len(titles) == 3

    # Sending the same page again stores nothing new
    again = (await _post(client, h, {"jobs": jobs})).json()
    assert again["duplicates"] == 8 and again["queued_ids"] == []


@pytest.mark.asyncio
async def test_other_users_rows_are_not_duplicates(client: AsyncClient, auth_headers_with_profile):
    async with TestSessionLocal() as db:
        other = User(email="other@example.com", hashed_password="x")
        db.add(other)
        await db.flush()
        db.add(JobQueueItem(user_id=other.id, upwork_url=_job(1)["upwork_url"], title="theirs"))
        await db.commit()
    data = (await _post(client, auth_headers_with_profile, {"jobs": [_job(1)]})).json()
    assert data["duplicates"] == 0 and data["suggested"] == 1


# ── pre-filter, cap, threshold, statuses ─────────────────────────────────────

@pytest.mark.asyncio
async def test_pre_filter_codes_and_profile_minimums(client: AsyncClient, auth_headers_with_profile):
    h = auth_headers_with_profile
    uid = await _user_id(client, h)
    await _set_profile(uid, minimum_budget=1500, minimum_hourly_rate=None, avoid_keywords=["wordpress"])
    jobs = [
        _job(1, budget_amount="$1,000"),                                  # under the profile floor (500 would pass)
        _job(2, budget_amount="$40 - $55", budget_type="hourly"),          # under the default hourly floor
        _job(3, posted_text="3 weeks ago"),
        _job(4, posted_at=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat()),
        _job(5, client_info={"location": "Pakistan"}),
        _job(6, title="WordPress plugin fix"),
        _job(7, budget_amount="$1,600"),                                  # passes
    ]
    scorer = _scorer()
    data = (await _post(client, h, {"jobs": jobs}, scorer)).json()
    assert data == {"received": 7, "duplicates": 0, "pre_filtered": 6, "scored": 1, "suggested": 1,
                    "below_threshold": 0, "queued_ids": data["queued_ids"]}
    by_title = {i.title: i for i in await _items(uid)}
    expect = {
        "FastAPI backend 1": "pre_filter:budget_too_low: $1000 < $1500",
        "FastAPI backend 2": "pre_filter:hourly_top_too_low: $55/hr < $60",
        "FastAPI backend 3": "pre_filter:too_old: 21d",
        "FastAPI backend 4": "pre_filter:too_old: 10d",
        "FastAPI backend 5": "pre_filter:blocked_country: Pakistan",
        "WordPress plugin fix": "pre_filter:avoid_keyword: 'wordpress'",
    }
    for title, reason in expect.items():
        assert by_title[title].status == "pre_filtered" and by_title[title].rejection_reason == reason
        assert by_title[title].ai_score is None
    assert by_title["FastAPI backend 7"].status == "suggested"

    # Without a profile minimum the default floor ($500) applies
    await _set_profile(uid, minimum_budget=None)
    data = (await _post(client, h, {"jobs": [_job(8, budget_amount="$1,000"), _job(9, budget_amount="$400")]})).json()
    assert data["scored"] == 1 and data["pre_filtered"] == 1


@pytest.mark.asyncio
async def test_a_full_request_is_all_scored(client: AsyncClient, auth_headers_with_profile):
    # A request holds at most MAX_SCORED_PER_REQUEST jobs, so none is left as score_cap_reached
    # (a stored capped job would be a duplicate on every later scan and never get scored).
    h = auth_headers_with_profile
    scorer = _scorer()
    data = (await _post(client, h, {"jobs": [_job(i) for i in range(25)]}, scorer)).json()
    assert len(scorer.calls) == 25
    assert data["scored"] == 25 and data["pre_filtered"] == 0


@pytest.mark.asyncio
async def test_threshold_from_autonomy_profile_and_statuses(client: AsyncClient, auth_headers_with_profile):
    h = auth_headers_with_profile
    uid = await _user_id(client, h)
    async with TestSessionLocal() as db:
        db.add(UserAutonomyProfile(user_id=uid, score_threshold=70.0))
        await db.commit()
    scorer = _scorer(75.0, 69.5, 70.0)
    data = (await _post(client, h, {"jobs": [_job(1), _job(2), _job(3)]}, scorer)).json()
    assert data["scored"] == 3 and data["suggested"] == 2 and data["below_threshold"] == 1
    assert data["pre_filtered"] == 0
    by_title = {i.title: i for i in await _items(uid)}
    low = by_title["FastAPI backend 2"]
    assert low.status == "pre_filtered" and low.rejection_reason == "pre_filter:below_threshold: 69.5"
    assert low.ai_score == 69.5
    for t in ("FastAPI backend 1", "FastAPI backend 3"):
        it = by_title[t]
        assert it.status == "suggested" and it.source == "extension_scan" and it.draft_status == "none"
        assert it.ai_reasoning.startswith(f"Score: {it.ai_score}. Strong Python fit.")
        assert it.chips == ["python", "fastapi", "postgresql", "backend"]
        assert it.expires_at - it.created_at > timedelta(days=6, hours=23)
    assert set(data["queued_ids"]) == {by_title["FastAPI backend 1"].id, by_title["FastAPI backend 3"].id}

    # The scorer got the real run_full_analysis signature
    call = scorer.calls[0]
    assert call["user_id"] == uid and call["job_title"] == "FastAPI backend 1"
    assert call["job_skills"] == ["Python", "PostgreSQL"] and call["budget_amount"] == "$2,000"
    assert set(call) >= {"db", "profile", "job_description", "client_info"}

    async with TestSessionLocal() as db:
        events = (await db.execute(select(OutcomeEvent).where(OutcomeEvent.user_id == uid))).scalars().all()
        ap = (await db.execute(select(UserAutonomyProfile).where(UserAutonomyProfile.user_id == uid))).scalar_one()
    assert sorted(e.job_queue_id for e in events if e.event_type == "suggested") == sorted(data["queued_ids"])
    assert ap.suggestions_shown == 2


@pytest.mark.asyncio
async def test_default_threshold_is_55(client: AsyncClient, auth_headers_with_profile):
    data = (await _post(client, auth_headers_with_profile, {"jobs": [_job(1), _job(2)]}, _scorer(55.0, 54.9))).json()
    assert data["suggested"] == 1 and data["below_threshold"] == 1


@pytest.mark.asyncio
async def test_below_threshold_items_can_be_scored_anyway(client: AsyncClient, auth_headers_with_profile):
    h = auth_headers_with_profile
    await _post(client, h, {"jobs": [_job(1)]}, _scorer(20.0))
    item = (await _items(await _user_id(client, h)))[0]
    listed = (await client.get("/api/v1/job-queue?status=pre_filtered", headers=h)).json()
    assert listed[0]["skip_reason"] == "pre_filter:below_threshold" and listed[0]["skip_reason_detail"] == "20"
    with patch("app.api.v1.job_queue._score_pre_filtered_background", AsyncMock()):
        r = await client.post(f"/api/v1/job-queue/{item.id}/score-anyway", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "suggested"


@pytest.mark.asyncio
async def test_requires_a_profile(client: AsyncClient, auth_headers):
    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as db:
        profile = (await db.execute(select(UserProfile).where(UserProfile.user_id == uid))).scalar_one()
        await db.delete(profile)
        await db.commit()
    r = await _post(client, auth_headers, {"jobs": [_job(1)]})
    assert r.status_code == 400


# ── search query stats + ownership ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_stats_update(client: AsyncClient, auth_headers_with_profile):
    h = auth_headers_with_profile
    q = (await client.post("/api/v1/search-queries", headers=h, json={"query": "fastapi postgres"})).json()
    # 2 scored (80, 60) + 1 pre-filtered + 1 duplicate in batch
    jobs = [_job(1), _job(2), _job(3, budget_amount="$50"), _job(1)]
    data = (await _post(client, h, {"query_id": q["id"], "query": "fastapi postgres", "jobs": jobs},
                        _scorer(80.0, 60.0))).json()
    assert data["scored"] == 2
    async with TestSessionLocal() as db:
        sq = (await db.execute(select(SearchQuery).where(SearchQuery.id == q["id"]))).scalar_one()
    assert sq.run_count == 1 and sq.last_run_at is not None
    assert sq.total_jobs_found == 2 and sq.avg_match_score == 70.0 and sq.high_score_count == 1
    items = await _items(await _user_id(client, h))
    assert all(i.source_query_id == q["id"] for i in items)

    # A second run folds into the rolling average
    await _post(client, h, {"query_id": q["id"], "jobs": [_job(4)]}, _scorer(40.0))
    async with TestSessionLocal() as db:
        sq = (await db.execute(select(SearchQuery).where(SearchQuery.id == q["id"]))).scalar_one()
    assert sq.run_count == 2 and sq.total_jobs_found == 3 and sq.avg_match_score == 60.0


@pytest.mark.asyncio
async def test_query_id_of_another_user_is_ignored(client: AsyncClient, auth_headers_with_profile):
    async with TestSessionLocal() as db:
        other = User(email="other2@example.com", hashed_password="x")
        db.add(other)
        await db.flush()
        theirs = SearchQuery(user_id=other.id, query="theirs")
        db.add(theirs)
        await db.commit()
        theirs_id = theirs.id
    h = auth_headers_with_profile
    r = await _post(client, h, {"query_id": theirs_id, "jobs": [_job(1)]})
    assert r.status_code == 200 and r.json()["suggested"] == 1
    async with TestSessionLocal() as db:
        sq = (await db.execute(select(SearchQuery).where(SearchQuery.id == theirs_id))).scalar_one()
    assert sq.run_count == 0 and sq.total_jobs_found == 0
    assert (await _items(await _user_id(client, h)))[0].source_query_id is None


# ── expiry on read ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_suggestions_expire_on_read(client: AsyncClient, auth_headers_with_profile):
    h = auth_headers_with_profile
    uid = await _user_id(client, h)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    async with TestSessionLocal() as db:
        other = User(email="other3@example.com", hashed_password="x")
        db.add(other)
        await db.flush()
        db.add_all([
            JobQueueItem(user_id=uid, upwork_url="https://www.upwork.com/jobs/~01stale", title="stale",
                         status="suggested", expires_at=past),
            JobQueueItem(user_id=uid, upwork_url="https://www.upwork.com/jobs/~01fresh", title="fresh",
                         status="suggested", expires_at=past + timedelta(days=3)),
            JobQueueItem(user_id=uid, upwork_url="https://www.upwork.com/jobs/~01appr", title="approved old",
                         status="approved", expires_at=past),
            JobQueueItem(user_id=other.id, upwork_url="https://www.upwork.com/jobs/~01theirs", title="theirs",
                         status="suggested", expires_at=past),
        ])
        await db.commit()

    listed = (await client.get("/api/v1/job-queue?status=suggested", headers=h)).json()
    assert [i["title"] for i in listed] == ["fresh"]
    statuses = {i.title: i.status for i in await _items(uid)}
    assert statuses == {"stale": "expired", "fresh": "suggested", "approved old": "approved"}
    async with TestSessionLocal() as db:
        theirs = (await db.execute(select(JobQueueItem).where(JobQueueItem.title == "theirs"))).scalar_one()
    assert theirs.status == "suggested"  # scoped to the reading user

    async with TestSessionLocal() as db:
        await db.execute(update(JobQueueItem).where(JobQueueItem.title == "fresh").values(expires_at=past))
        await db.commit()
    assert (await client.get("/api/v1/job-queue/stats", headers=h)).status_code == 200
    assert {i.title: i.status for i in await _items(uid)}["fresh"] == "expired"


# ── helpers ──────────────────────────────────────────────────────────────────

def test_upwork_job_slug():
    assert upwork_job_slug("https://www.upwork.com/jobs/Title_~01ABcd123/?x=1") == "01abcd123"
    assert upwork_job_slug("https://www.upwork.com/jobs/plain") is None
    assert upwork_job_slug(None) is None


def test_parse_posted_at():
    assert parse_posted_at("2026-10-30T12:00:00Z") == datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    assert parse_posted_at("2026-10-30T12:00:00").tzinfo == timezone.utc
    assert parse_posted_at("yesterday") is None and parse_posted_at(None) is None


def test_derive_chips():
    assert derive_chips("Full-stack SaaS MVP with React", ["Postgres", "OpenAI API"]) == \
        ["react", "postgresql", "llm", "saas", "mvp", "fullstack"]
    assert derive_chips("Plumbing", []) == []
    assert len(derive_chips("python fastapi react typescript sql azure aws", [])) == 6


@pytest.mark.asyncio
async def test_max_age_days_sets_the_lookback(client: AsyncClient, auth_headers_with_profile):
    h = auth_headers_with_profile
    ten_days = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    # Default (7 days): a 10-day-old job is too old
    data = (await _post(client, h, {"jobs": [_job(1, posted_at=ten_days)]})).json()
    assert data["pre_filtered"] == 1 and data["scored"] == 0
    # A 14-day lookback scores it
    data = (await _post(client, h, {"max_age_days": 14, "jobs": [_job(2, posted_at=ten_days)]})).json()
    assert data["scored"] == 1 and data["pre_filtered"] == 0
    # Out of range is rejected
    assert (await _post(client, h, {"max_age_days": 31, "jobs": [_job(3)]})).status_code == 422
