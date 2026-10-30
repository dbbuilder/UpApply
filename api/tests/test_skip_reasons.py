"""Canonical skip reasons: normalisation, legacy read-time mapping, and wiring into the job queue."""
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import select

from app.models.job_queue import JobQueueItem
from app.models.outcome_event import OutcomeEvent
from app.schemas.job_queue import JobQueueItemResponse
from app.services.skip_reasons import (
    OTHER,
    PRE_FILTER_CODES,
    USER_REASONS,
    encode,
    normalise_pre_filter,
    normalise_user_reason,
    parse_stored,
)
from tests.conftest import TestSessionLocal


def test_known_codes_and_notes():
    for code in USER_REASONS:
        assert normalise_user_reason(code) == (code, None)
    assert normalise_user_reason("budget_too_low: wants $50 for a full app") == (
        "budget_too_low", "wants $50 for a full app")
    assert normalise_user_reason("  client_risk  ") == ("client_risk", None)
    assert normalise_user_reason(None) is None
    assert normalise_user_reason("   ") is None


def test_free_text_becomes_other_with_text_kept():
    assert normalise_user_reason("Client wants a Rust kernel dev") == (OTHER, "Client wants a Rust kernel dev")
    assert normalise_user_reason("Budget: too low") == (OTHER, "Budget: too low")
    # a user cannot claim an automatic pre-filter code
    assert normalise_user_reason("pre_filter:too_old") == (OTHER, "pre_filter:too_old")


def test_legacy_extension_labels_map_exactly():
    assert normalise_user_reason("Budget too low") == ("budget_too_low", None)
    assert normalise_user_reason("Not my specialty") == ("wrong_skills", None)
    assert normalise_user_reason("Too large / long") == ("too_large", None)
    assert normalise_user_reason("Client looks risky") == ("client_risk", None)
    assert normalise_user_reason("Already applied") == ("duplicate", None)
    assert normalise_user_reason("Other") == (OTHER, None)
    assert normalise_user_reason("Budget is too low") == (OTHER, "Budget is too low")


def test_pre_filter_rules_from_the_agent():
    assert normalise_pre_filter("blocked_country (India)") == ("pre_filter:blocked_country", "India")
    assert normalise_pre_filter("budget_too_low ($300 < $500)") == ("pre_filter:budget_too_low", "$300 < $500")
    assert normalise_pre_filter("hourly_top_too_low ($25/hr < $50)")[0] == "pre_filter:hourly_top_too_low"
    assert normalise_pre_filter("too_old (9d)") == ("pre_filter:too_old", "9d")
    assert normalise_pre_filter("avoid_keyword ('wordpress')") == ("pre_filter:avoid_keyword", "'wordpress'")
    assert normalise_pre_filter("score_cap_reached (40)") == ("pre_filter:score_cap_reached", "40")
    assert normalise_pre_filter("pre_filter:too_old: 9d") == ("pre_filter:too_old", "9d")
    assert normalise_pre_filter("new_rule (x)") == (OTHER, "new_rule (x)")
    assert normalise_pre_filter("") is None


def test_parse_stored_round_trips_and_maps_legacy_rows():
    for code in USER_REASONS:
        assert parse_stored(encode(code, "note"), "rejected") == (code, "note")
    for code in PRE_FILTER_CODES:
        assert parse_stored(encode(code), "pre_filtered") == (code, None)
    # legacy rows: raw pre-filter strings and old free text
    assert parse_stored("blocked_country (India)", "pre_filtered") == ("pre_filter:blocked_country", "India")
    assert parse_stored("budget_too_low", "pre_filtered") == ("pre_filter:budget_too_low", None)
    assert parse_stored("budget_too_low", "rejected") == ("budget_too_low", None)
    assert parse_stored("Client looks risky", "rejected") == ("client_risk", None)
    assert parse_stored("weird client", "rejected") == (OTHER, "weird client")
    assert parse_stored(None, "rejected") == (None, None)


def test_response_exposes_mapped_skip_reason():
    base = dict(id="i", user_id="u", upwork_url="x", title="t", source="agent",
                created_at="2026-10-30T00:00:00Z")
    r = JobQueueItemResponse(**base, status="rejected", rejection_reason="Not my specialty")
    assert (r.skip_reason, r.skip_reason_detail) == ("wrong_skills", None)
    r = JobQueueItemResponse(**base, status="pre_filtered", rejection_reason="blocked_country (India)")
    assert (r.skip_reason, r.skip_reason_detail) == ("pre_filter:blocked_country", "India")
    assert JobQueueItemResponse(**base, status="suggested").model_dump()["skip_reason"] is None


async def _add(client, headers, url, **extra):
    resp = await client.post("/api/v1/job-queue", headers=headers,
                             json={"upwork_url": url, "title": "Job", **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _events(item_id, event_type):
    async with TestSessionLocal() as s:
        return (await s.execute(select(OutcomeEvent).where(
            OutcomeEvent.job_queue_id == item_id, OutcomeEvent.event_type == event_type))).scalars().all()


async def test_user_reject_stores_canonical_code(client: AsyncClient, auth_headers: dict):
    coded = await _add(client, auth_headers, "https://www.upwork.com/jobs/~a")
    resp = await client.put(f"/api/v1/job-queue/{coded['id']}/action", headers=auth_headers,
                            json={"action": "reject", "rejection_reason": "too_many_proposals"})
    assert resp.status_code == 200
    body = resp.json()
    assert (body["status"], body["rejection_reason"], body["skip_reason"]) == (
        "rejected", "too_many_proposals", "too_many_proposals")
    [event] = await _events(coded["id"], "rejected")
    assert event.meta["skip_reason"] == "too_many_proposals"

    free = await _add(client, auth_headers, "https://www.upwork.com/jobs/~b")
    body = (await client.put(f"/api/v1/job-queue/{free['id']}/action", headers=auth_headers,
                             json={"action": "reject", "rejection_reason": "Needs on-site in Oslo"})).json()
    assert body["rejection_reason"] == "other: Needs on-site in Oslo"
    assert (body["skip_reason"], body["skip_reason_detail"]) == ("other", "Needs on-site in Oslo")

    legacy = await _add(client, auth_headers, "https://www.upwork.com/jobs/~c")
    body = (await client.put(f"/api/v1/job-queue/{legacy['id']}/action", headers=auth_headers,
                             json={"action": "reject", "rejection_reason": "Budget too low"})).json()
    assert body["rejection_reason"] == "budget_too_low"


async def test_pre_filter_block_records_code_and_score_anyway_keeps_it(client: AsyncClient, auth_headers: dict):
    item = await _add(client, auth_headers, "https://www.upwork.com/jobs/~d",
                      filter_reason="blocked_country (India)")
    assert item["status"] == "pre_filtered"
    assert item["rejection_reason"] == "pre_filter:blocked_country: India"
    assert (item["skip_reason"], item["skip_reason_detail"]) == ("pre_filter:blocked_country", "India")

    with patch("app.api.v1.job_queue._score_pre_filtered_background"):
        resp = await client.post(f"/api/v1/job-queue/{item['id']}/score-anyway", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "suggested" and resp.json()["rejection_reason"] is None
    [event] = await _events(item["id"], "score_anyway")
    assert event.meta == {"skip_reason": "pre_filter:blocked_country", "skip_reason_detail": "India"}

    async with TestSessionLocal() as s:
        row = (await s.execute(select(JobQueueItem).where(JobQueueItem.id == item["id"]))).scalar_one()
    assert row.rejection_reason is None
