"""Outcome mapping (pure) and apply_outcome crediting (DB)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.outcomes import (
    NO_RESPONSE_AFTER,
    POSITIVE_OUTCOMES,
    apply_outcome,
    parse_submitted_at,
    resolve_outcome,
    should_replace,
)

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("raw,expected", [
    ("responded", "replied"),       # extension list scraper: active_candidacies
    ("interviewed", "interviewed"),
    ("hired", "hired"),
    ("declined", "declined"),
    ("viewed", "viewed"),
    ("Replied", "replied"),
    ("no_response", "no_response"),
])
def test_status_maps_to_outcome(raw, expected):
    assert resolve_outcome(raw, NOW - timedelta(days=1), NOW) == expected


def test_submitted_is_no_signal_until_14_days():
    assert resolve_outcome("submitted", NOW - timedelta(days=13), NOW) is None
    assert resolve_outcome("submitted", NOW - NO_RESPONSE_AFTER, NOW) == "no_response"
    assert resolve_outcome("submitted", None, NOW) is None


def test_unknown_status_ignored_unless_stale():
    assert resolve_outcome("withdrawn-ish", NOW - timedelta(days=2), NOW) is None


def test_should_replace_is_monotonic():
    assert should_replace(None, "viewed")
    assert should_replace("no_response", "replied")
    assert should_replace("replied", "hired")
    assert not should_replace("hired", "replied")
    assert not should_replace("replied", "declined")
    assert not should_replace("viewed", None)
    assert not should_replace("hired", "hired")


def test_positive_outcomes():
    assert POSITIVE_OUTCOMES == {"replied", "interviewed", "hired"}


def test_parse_submitted_at():
    assert parse_submitted_at("Mar 3, 2026") == datetime(2026, 3, 3, tzinfo=timezone.utc)
    assert parse_submitted_at("2026-03-03T10:00:00+00:00") == datetime(2026, 3, 3, 10, tzinfo=timezone.utc)
    assert parse_submitted_at("yesterday") is None
    assert parse_submitted_at(None) is None


# --- apply_outcome (DB) -------------------------------------------------------


async def _make_user(db, email):
    from app.models.user import User

    user = User(email=email, hashed_password="not-a-real-hash")
    db.add(user)
    await db.flush()
    return user


async def _fact(db, user_id, statement="Led a 120-server Azure migration."):
    from app.models.fact import Fact

    fact = Fact(
        user_id=user_id, kind="metric", statement=statement, status="approved",
        source_type="bio_memory", source_ref="m1", sources=[],
    )
    db.add(fact)
    await db.flush()
    return fact


async def _proposal_with_letter(db, user_id, fact_ids, letter_user_id=None):
    from app.models.cover_letter import CoverLetter
    from app.models.job import Job
    from app.models.proposal import Proposal

    job = Job(user_id=user_id, upwork_url="https://www.upwork.com/jobs/~01", title="T", description="D")
    db.add(job)
    await db.flush()
    db.add(CoverLetter(
        user_id=letter_user_id or user_id, job_id=job.id, content="draft", model_used="m",
        fact_ids_used=[str(i) for i in fact_ids], final_text="final",
    ))
    proposal = Proposal(user_id=user_id, job_id=job.id, cover_letter_text="final", outcome=None)
    db.add(proposal)
    await db.flush()
    return proposal


async def test_apply_outcome_credits_won_facts_once(db_session):
    user = await _make_user(db_session, "outcomes-a@example.com")
    fact = await _fact(db_session, user.id)
    proposal = await _proposal_with_letter(db_session, user.id, [fact.id])

    assert await apply_outcome(db_session, proposal, "replied") is True
    assert proposal.outcome == "replied"
    assert proposal.client_responded is True
    assert proposal.facts_credited_at is not None
    # Re-sync with the same and a later positive status never double-credits.
    assert await apply_outcome(db_session, proposal, "replied") is False
    assert await apply_outcome(db_session, proposal, "hired") is False
    assert proposal.outcome == "hired" and proposal.was_hired is True

    await db_session.refresh(fact)
    assert fact.times_in_won == 1


async def test_apply_outcome_credit_marker_survives_reloaded_positive_state(db_session):
    """A legacy positive row with the marker already set is never credited again."""
    user = await _make_user(db_session, "outcomes-b@example.com")
    fact = await _fact(db_session, user.id)
    proposal = await _proposal_with_letter(db_session, user.id, [fact.id])
    proposal.facts_credited_at = NOW
    await db_session.flush()

    assert await apply_outcome(db_session, proposal, "interviewed") is False
    await db_session.refresh(fact)
    assert fact.times_in_won == 0


async def test_apply_outcome_non_positive_does_not_credit(db_session):
    user = await _make_user(db_session, "outcomes-c@example.com")
    fact = await _fact(db_session, user.id)
    proposal = await _proposal_with_letter(db_session, user.id, [fact.id])

    assert await apply_outcome(db_session, proposal, "viewed") is False
    assert await apply_outcome(db_session, proposal, "declined") is False
    assert proposal.outcome == "declined"
    assert proposal.facts_credited_at is None
    # Monotonic: declined can still advance to a reply, which then credits.
    assert await apply_outcome(db_session, proposal, "replied") is True
    await db_session.refresh(fact)
    assert fact.times_in_won == 1


async def test_apply_outcome_never_downgrades(db_session):
    user = await _make_user(db_session, "outcomes-d@example.com")
    proposal = await _proposal_with_letter(db_session, user.id, [])
    proposal.outcome = "hired"
    assert await apply_outcome(db_session, proposal, "declined") is False
    assert await apply_outcome(db_session, proposal, "no_response") is False
    assert proposal.outcome == "hired"


async def test_apply_outcome_is_user_scoped(db_session):
    owner = await _make_user(db_session, "outcomes-e@example.com")
    other = await _make_user(db_session, "outcomes-f@example.com")
    theirs = await _fact(db_session, other.id)
    # Another user's letter on the same job, citing their own fact, must not be used.
    proposal = await _proposal_with_letter(db_session, owner.id, [theirs.id], letter_user_id=other.id)

    assert await apply_outcome(db_session, proposal, "hired") is False
    await db_session.refresh(theirs)
    assert theirs.times_in_won == 0


async def test_apply_outcome_does_not_credit_rejected_facts(db_session):
    user = await _make_user(db_session, "outcomes-g@example.com")
    kept = await _fact(db_session, user.id)
    rejected = await _fact(db_session, user.id, statement="Cut Azure spend by 90%.")
    rejected.status = "rejected"
    proposal = await _proposal_with_letter(db_session, user.id, [kept.id, rejected.id])

    assert await apply_outcome(db_session, proposal, "replied") is True
    await db_session.refresh(kept)
    await db_session.refresh(rejected)
    assert kept.times_in_won == 1
    assert rejected.times_in_won == 0
