"""Canonical proposal stages: alias map, stage sync on status, append-only transition ledger."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.proposal import Proposal
from app.models.proposal_stage_event import ProposalStageEvent
from app.services.proposal_status import STAGE_ALIASES, STAGES, advance_status, set_status, stage_for
from tests.conftest import TestSessionLocal


@pytest.mark.parametrize("raw,stage", [
    ("7", "submitted"),            # the one confirmed Upwork numeric code
    ("submitted", "submitted"),
    ("Viewed", "viewed"),
    (" responded ", "replied"),
    ("replied", "replied"),
    ("interviewed", "interview"),
    ("hired", "hired"),
    ("declined", "declined"),
    ("archived", "closed"),
    ("withdrawn", "closed"),
])
def test_aliases(raw, stage):
    assert stage_for(raw) == stage


@pytest.mark.parametrize("raw", ["8", "2", "3", "10", "active", "imported", "offered", "", None])
def test_unconfirmed_codes_and_strings_are_unknown(raw):
    assert stage_for(raw) == "unknown"


def test_alias_targets_are_canonical_stages():
    assert set(STAGE_ALIASES.values()) <= set(STAGES)
    assert all(k == k.strip().lower() for k in STAGE_ALIASES)


def test_status_assignment_sets_stage():
    p = Proposal(cover_letter_text="x", status="responded")
    assert p.stage == "replied"
    p.status = "8"
    assert p.stage == "unknown"


def test_advance_status_only_moves_forward():
    p = Proposal(cover_letter_text="x", status="8")
    assert advance_status(p, "submitted", "outcome_sync") and p.stage == "submitted"
    assert advance_status(p, "responded", "outcome_sync") and p.status == "responded"
    assert not advance_status(p, "submitted", "outcome_sync")  # archived row re-synced as submitted
    assert not advance_status(p, "declined", "outcome_sync")   # a reply is never overwritten
    assert not advance_status(p, "8", "outcome_sync")          # unknown never replaces a known stage
    assert p.stage == "replied" and p.status == "responded"
    assert advance_status(p, "Hired", "outcome_sync") and p.stage == "hired"


async def _user(s):
    from app.models.user import User
    u = User(email=f"stage-{datetime.now().timestamp()}@example.com", hashed_password="x")
    s.add(u)
    await s.flush()
    return u


async def _events(pid):
    async with TestSessionLocal() as s:
        return [(e.from_stage, e.to_stage, e.raw_status, e.source) for e in (await s.execute(
            select(ProposalStageEvent).where(ProposalStageEvent.proposal_id == pid)
            .order_by(ProposalStageEvent.created_at, ProposalStageEvent.id)
        )).scalars()]


async def test_ledger_records_creation_and_each_change(db_session):
    user = await _user(db_session)
    p = Proposal(user_id=user.id, cover_letter_text="x", status="submitted", source="scraped")
    db_session.add(p)
    await db_session.commit()
    assert await _events(p.id) == [(None, "submitted", "submitted", "scraped")]

    p.status = "Submitted"  # same stage: no row
    p.cover_letter_text = "y"
    await db_session.commit()
    assert len(await _events(p.id)) == 1

    set_status(p, "responded", "outcome_sync")
    await db_session.commit()
    p.status = "8"  # direct write (e.g. PUT): source falls back to "api"
    await db_session.commit()
    assert (await _events(p.id))[1:] == [
        ("submitted", "replied", "responded", "outcome_sync"),
        ("replied", "unknown", "8", "api"),
    ]
    assert p.stage == "unknown"


async def test_ledger_row_for_proposal_created_without_status(db_session):
    user = await _user(db_session)
    p = Proposal(user_id=user.id, cover_letter_text="x", source="extension")
    db_session.add(p)
    await db_session.commit()
    assert p.stage == "unknown"
    assert await _events(p.id) == [(None, "unknown", None, "extension")]


async def test_outcome_sync_advances_stage_and_ledger(client, auth_headers):
    uid = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()["id"]
    async with TestSessionLocal() as s:
        p = Proposal(user_id=uid, upwork_proposal_id="555", cover_letter_text="x", status="8",
                     source="scraped", submitted_at=datetime.now(timezone.utc) - timedelta(days=2))
        s.add(p)
        await s.commit()
    url = "/api/v1/proposals/outcomes"
    for status in ("viewed", "responded", "submitted"):
        r = await client.post(url, headers=auth_headers,
                              json={"items": [{"upwork_proposal_id": "555", "status": status}]})
        assert r.status_code == 200, r.text
    async with TestSessionLocal() as s:
        row = (await s.execute(select(Proposal).where(Proposal.id == p.id))).scalar_one()
    assert (row.status, row.stage, row.outcome) == ("responded", "replied", "replied")
    assert await _events(p.id) == [
        (None, "unknown", "8", "scraped"),
        ("unknown", "viewed", "viewed", "outcome_sync"),
        ("viewed", "replied", "responded", "outcome_sync"),
    ]


async def test_put_status_updates_stage(client, auth_headers):
    uid = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()["id"]
    async with TestSessionLocal() as s:
        p = Proposal(user_id=uid, cover_letter_text="x", status="submitted", source="manual")
        s.add(p)
        await s.commit()
    r = await client.put(f"/api/v1/proposals/{p.id}", headers=auth_headers, json={"status": "hired"})
    assert r.status_code == 200, r.text
    assert (await _events(p.id))[-1] == ("submitted", "hired", "hired", "api")
