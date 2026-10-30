"""Client trust card: rule table, missing-data neutrality, repost detection, API exposure."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.job import Job
from app.models.job_queue import JobQueueItem
from app.services.client_trust import (
    TIER_CAUTION,
    TIER_HIGH,
    TIER_SUSPICIOUS,
    assess_client_trust,
    client_trust_for,
    count_reposts,
    job_key,
    normalise_title,
    recent_title_index,
)
from app.services.job_analysis import AnalysisResult

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def _signal(card, label):
    found = [s for s in card["signals"] if s["label"] == label]
    return found[0] if found else None


# ── Rule table ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("client_info, label, effect", [
    ({"payment_verified": True}, "Payment method", "positive"),
    ({"paymentVerified": False}, "Payment method", "caution"),
    ({"payment_verified": "Payment unverified"}, "Payment method", "caution"),
    ({"total_spent": "$50K+ total spent"}, "Total spent", "positive"),
    ({"totalSpent": "$0"}, "Total spent", "caution"),
    ({"total_spent": "$0", "total_hires": 2}, "Total spent", "neutral"),
    ({"total_spent": "$900"}, "Total spent", "neutral"),
    ({"hire_rate": "80% hire rate"}, "Hire rate", "positive"),
    ({"hire_rate": "10%", "jobs_posted": 12}, "Hire rate", "caution"),
    ({"hire_rate": "10%", "jobs_posted": 2}, "Hire rate", "neutral"),
    ({"hire_rate": "10%"}, "Hire rate", "neutral"),  # jobs posted unknown: not enough to judge
    ({"rating": 4.9}, "Client rating", "positive"),
    ({"rating": "Rating is 3.2 out of 5"}, "Client rating", "caution"),
    ({"rating": 4.2}, "Client rating", "neutral"),
    ({"rating": 0}, "Client rating", "neutral"),  # no reviews yet
    ({"proposals": "50+"}, "Proposals so far", "caution"),
    ({"proposals": "10 to 15"}, "Proposals so far", "neutral"),
    ({"location": "United States"}, "Location", "neutral"),
    ({"member_since": "Mar 2019"}, "Member since", "neutral"),
])
def test_rule_table(client_info, label, effect):
    signal = _signal(assess_client_trust(client_info, now=NOW), label)
    assert signal is not None and signal["effect"] == effect


def test_long_open_job_is_a_caution_and_a_fresh_one_adds_nothing():
    old = assess_client_trust({}, posted_at=NOW - timedelta(days=45), now=NOW)
    assert _signal(old, "Posted")["effect"] == "caution"
    assert _signal(assess_client_trust({}, posted_at=NOW - timedelta(days=2), now=NOW), "Posted") is None


def test_repost_count_becomes_a_caution():
    card = assess_client_trust({}, repost_count=2, now=NOW)
    assert _signal(card, "Reposted")["value"].startswith("Same title seen 2 times")
    assert card["tier"] == TIER_CAUTION


def test_tiers():
    assert assess_client_trust(
        {"payment_verified": True, "total_spent": "$20K", "rating": 4.8}, now=NOW
    )["tier"] == TIER_HIGH
    assert assess_client_trust({"payment_verified": False, "rating": 4.8}, now=NOW)["tier"] == TIER_CAUTION
    assert assess_client_trust(
        {"payment_verified": False, "total_spent": "$0", "rating": 3.0}, now=NOW
    )["tier"] == TIER_SUSPICIOUS


# ── Missing data is neutral ──────────────────────────────────────────────────

@pytest.mark.parametrize("client_info", [
    None, {}, {"rating": None, "location": None, "hire_rate": None, "total_spent": None, "member_since": None},
    {"rating": "No feedback yet", "total_spent": "", "hire_rate": "n/a", "paymentVerified": None},
])
def test_missing_data_is_never_negative(client_info):
    card = assess_client_trust(client_info, now=NOW)
    assert card["tier"] == TIER_HIGH
    assert all(s["effect"] != "caution" for s in card["signals"])
    assert any("limited data" in note for note in card["notes"])


def test_wording_never_accuses_the_client():
    card = assess_client_trust(
        {"payment_verified": False, "total_spent": "$0", "rating": 2.0, "proposals": "50+"},
        posted_at=NOW - timedelta(days=60), repost_count=3, now=NOW,
    )
    text = " ".join(f"{s['label']} {s['value']}" for s in card["signals"]).lower()
    for word in ("scam", "fraud", "fake", "suspicious", "spam"):
        assert word not in text


def test_title_and_url_normalisation():
    assert normalise_title("  Build a React/Node APP!! ") == "build a react node app"
    assert job_key("https://www.upwork.com/jobs/~01abc123def4567890?source=rss") == "1abc123def4567890"
    assert job_key("https://www.upwork.com/nx/jobs/~01abc123def4567890/") == "1abc123def4567890"


def test_count_reposts_excludes_the_job_itself_and_needs_a_url():
    index = {"react app": {"a1234567890", "b1234567890"}}
    assert count_reposts(index, "React App", "https://www.upwork.com/jobs/~0a1234567890") == 1
    assert count_reposts(index, "React App", None) == 0


# ── Repost detection (DB) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_repost_detection_across_jobs_and_queue(db_session, test_user):
    now = datetime.now(timezone.utc)
    db_session.add_all([
        Job(user_id=test_user.id, upwork_url="https://www.upwork.com/jobs/~01aaaaaaaaaaaa",
            title="Shopify store redesign!", description="d"),
        JobQueueItem(user_id=test_user.id, upwork_url="https://www.upwork.com/jobs/~01bbbbbbbbbbbb",
                     title="shopify   STORE redesign", created_at=now - timedelta(days=3)),
        # Too old to count
        JobQueueItem(user_id=test_user.id, upwork_url="https://www.upwork.com/jobs/~01cccccccccccc",
                     title="Shopify store redesign", created_at=now - timedelta(days=45)),
        # Different title
        Job(user_id=test_user.id, upwork_url="https://www.upwork.com/jobs/~01dddddddddddd",
            title="Shopify app", description="d"),
    ])
    await db_session.commit()

    index = await recent_title_index(db_session, test_user.id)
    # Seen in jobs and in the queue, a new posting with the same title counts both.
    assert count_reposts(index, "Shopify Store Redesign", "https://www.upwork.com/jobs/~01eeeeeeeeeeee") == 2
    # The saved job itself is not its own repost.
    assert count_reposts(index, "Shopify store redesign!", "https://www.upwork.com/jobs/~01aaaaaaaaaaaa") == 1

    card = await client_trust_for(db_session, test_user.id, client_info=None,
                                  title="Shopify app", upwork_url="https://www.upwork.com/jobs/~01dddddddddddd")
    assert _signal(card, "Reposted") is None


# ── API exposure: client_trust present, match_score untouched ────────────────

def _analysis(score=73.0):
    return AnalysisResult(match_score=score, skill_matches=[], missing_skills=[], strengths=[],
                          concerns=[], deal_breaker_warnings=[], relevant_memories=[],
                          recommendation="Apply")


@pytest.mark.asyncio
async def test_analyze_returns_client_trust_and_keeps_match_score(client, auth_headers_with_profile):
    body = {"title": "Data pipeline", "description": "Build an ETL pipeline",
            "upwork_url": "https://www.upwork.com/jobs/~01ffffffffffff"}
    with patch("app.api.v1.jobs.run_full_analysis", AsyncMock(return_value=_analysis())):
        plain = await client.post("/api/v1/jobs/analyze", json=body, headers=auth_headers_with_profile)
        risky = await client.post("/api/v1/jobs/analyze", headers=auth_headers_with_profile, json={
            **body, "client_info": {"rating": 3.1, "total_spent": "$0", "hire_rate": "5%"}})
    assert plain.status_code == 200 and risky.status_code == 200
    assert plain.json()["match_score"] == risky.json()["match_score"] == 73.0
    assert plain.json()["client_trust"]["tier"] == TIER_HIGH
    trust = risky.json()["client_trust"]
    assert trust["tier"] == TIER_CAUTION
    assert {"label": "Total spent", "value": "No spend or hires on Upwork yet", "effect": "caution"} in trust["signals"]


@pytest.mark.asyncio
async def test_create_job_returns_client_trust_and_stored_match_score(client, auth_headers_with_profile):
    with patch("app.api.v1.jobs.generate_embedding", AsyncMock(return_value=None)), \
         patch("app.api.v1.jobs.run_full_analysis", AsyncMock(return_value=_analysis(61.0))):
        resp = await client.post("/api/v1/jobs", headers=auth_headers_with_profile, json={
            "upwork_url": "https://www.upwork.com/jobs/~01gggggggggggg", "title": "Mobile app",
            "description": "Flutter app", "client_info": {"total_spent": "$25K", "rating": 4.9}})
    assert resp.status_code == 201
    data = resp.json()
    assert data["match_score"] == 61.0
    assert data["client_trust"]["tier"] == TIER_HIGH
    assert _signal(data["client_trust"], "Reposted") is None  # the job is not its own repost


@pytest.mark.asyncio
async def test_job_queue_list_includes_client_trust_with_reposts(client, auth_headers_with_profile):
    for suffix in ("hhhhhhhhhhhh", "iiiiiiiiiiii"):
        resp = await client.post("/api/v1/job-queue", headers=auth_headers_with_profile, json={
            "upwork_url": f"https://www.upwork.com/jobs/~01{suffix}", "title": "Power BI dashboard",
            "ai_score": 55, "client_info": {"paymentVerified": True, "totalSpent": "$3K"}})
        assert resp.status_code == 201
    items = (await client.get("/api/v1/job-queue", headers=auth_headers_with_profile)).json()
    assert len(items) == 2
    for item in items:
        assert item["ai_score"] == 55
        assert item["client_trust"]["tier"] == TIER_CAUTION
        assert _signal(item["client_trust"], "Reposted")["value"].startswith("Same title seen once")
        assert _signal(item["client_trust"], "Payment method")["effect"] == "positive"
