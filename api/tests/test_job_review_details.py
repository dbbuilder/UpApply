"""job_reviews.details (migration 031): card details kept with a scored job for the Find tab."""
import pytest
from httpx import AsyncClient

URL = "/api/v1/job-reviews"
DETAILS = {"posted_at": "2026-11-15T10:00:00Z", "posted_text": "Posted 3 hours ago",
           "client_country": "United States", "client_spent": "$90K+", "client_rating": "5.0",
           "payment_verified": True, "proposals": "5 to 10", "experience_level": "Expert"}


def _review(**kw):
    body = {"upwork_job_url": "https://www.upwork.com/jobs/~021", "job_title": "Fractional CTO", "ai_score": 88,
            "chips": ["$80-$120/hr"], "budget_amount": "$80-$120", "budget_type": "hourly"}
    body.update(kw)
    return body


@pytest.mark.asyncio
async def test_details_are_stored_and_listed(client: AsyncClient, auth_headers):
    resp = await client.post(URL, headers=auth_headers, json=_review(details=DETAILS))
    assert resp.status_code in (200, 201), resp.text
    listed = (await client.get(URL, headers=auth_headers)).json()["reviews"][0]
    assert listed["details"]["client_country"] == "United States"
    assert listed["details"]["posted_at"].startswith("2026-11-15T10:00:00")
    assert listed["details"]["payment_verified"] is True


@pytest.mark.asyncio
async def test_a_rescore_without_details_keeps_them(client: AsyncClient, auth_headers):
    await client.post(URL, headers=auth_headers, json=_review(details=DETAILS))
    await client.post(URL, headers=auth_headers, json=_review(ai_score=91))
    listed = (await client.get(URL, headers=auth_headers)).json()["reviews"][0]
    assert listed["ai_score"] == 91 and listed["details"]["proposals"] == "5 to 10"


@pytest.mark.asyncio
async def test_oversized_or_unknown_detail_fields(client: AsyncClient, auth_headers):
    bad = await client.post(URL, headers=auth_headers, json=_review(details={"client_country": "x" * 81}))
    assert bad.status_code == 422
    ok = await client.post(URL, headers=auth_headers, json=_review(details={"surprise": "dropped", "proposals": "50+"}))
    assert ok.status_code in (200, 201)
    listed = (await client.get(URL, headers=auth_headers)).json()["reviews"][0]
    assert listed["details"] == {"proposals": "50+"}
