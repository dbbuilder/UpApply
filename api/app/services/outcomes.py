"""Outcome sync (spec §3.3): Upwork proposal statuses → voice-sample outcomes → fact credit.

Replaces learning_engine.winning_proposal_to_memory. A won letter credits the facts
it used (times_in_won), which feeds the evidence rerank win_signal.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cover_letter import CoverLetter
from app.models.fact import Fact
from app.models.proposal import Proposal
from app.services.facts import credit_facts
from app.services.proposal_status import stage_for

NO_RESPONSE_AFTER = timedelta(days=14)
POSITIVE_OUTCOMES = frozenset({"replied", "interviewed", "hired"})

# Canonical stage (app.services.proposal_status) → outcome. None = no signal yet.
STAGE_TO_OUTCOME: dict[str, Optional[str]] = {
    "viewed": "viewed",
    "replied": "replied",
    "interview": "interviewed",
    "hired": "hired",
    "declined": "declined",
}

# Outcomes only move forward; a reply is never overwritten by a later decline.
_RANK: dict[Optional[str], int] = {
    None: 0, "no_response": 1, "viewed": 2, "declined": 3,
    "replied": 4, "interviewed": 5, "hired": 6,
}


def parse_submitted_at(value: Optional[str]) -> Optional[datetime]:
    """Parse Upwork's 'Mar 3, 2026' or an ISO timestamp into an aware UTC datetime."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%b %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def resolve_outcome(
    raw_status: str, submitted_at: Optional[datetime], now: Optional[datetime] = None
) -> Optional[str]:
    """Map a raw status to an outcome; silent proposals older than 14 days → no_response."""
    if raw_status.strip().lower() == "no_response":  # a client verdict, not an Upwork stage
        return "no_response"
    outcome = STAGE_TO_OUTCOME.get(stage_for(raw_status))
    if outcome is None and submitted_at is not None:
        now = now or datetime.now(timezone.utc)
        if now - submitted_at >= NO_RESPONSE_AFTER:
            return "no_response"
    return outcome


def should_replace(current: Optional[str], new: Optional[str]) -> bool:
    return new in _RANK and new is not None and _RANK[new] > _RANK.get(current, 0)


async def find_sent_letter(db: AsyncSession, user_id: str, job_id: Optional[str]) -> Optional[CoverLetter]:
    """The letter actually sent for a proposal's job: captured on Upwork (final_text), else
    marked submitted in the sidebar (was_submitted), else the newest draft for the job."""
    if not job_id:
        return None
    return (await db.execute(
        select(CoverLetter)
        .where(CoverLetter.user_id == user_id, CoverLetter.job_id == job_id)
        .order_by(
            CoverLetter.final_text.is_(None),
            CoverLetter.was_submitted.is_not(True),
            CoverLetter.created_at.desc(),
        )
        .limit(1)
    )).scalar_one_or_none()


async def apply_outcome(db: AsyncSession, proposal: Proposal, outcome: Optional[str]) -> bool:
    """Advance the proposal's outcome; credit facts on its first positive outcome.

    Crediting is idempotent: proposals.facts_credited_at is claimed with a conditional
    UPDATE, so re-syncs (or concurrent syncs) credit a proposal at most once.
    Returns True when facts were credited.
    """
    if not should_replace(proposal.outcome, outcome):
        return False
    was_positive = proposal.outcome in POSITIVE_OUTCOMES
    proposal.outcome = outcome
    if outcome in POSITIVE_OUTCOMES:
        proposal.client_responded = True
    if outcome == "hired":
        proposal.was_hired = True
    if was_positive or outcome not in POSITIVE_OUTCOMES or not proposal.job_id:
        return False
    if proposal.facts_credited_at is not None:
        return False

    letter = await find_sent_letter(db, proposal.user_id, proposal.job_id)
    if not letter or not letter.fact_ids_used:
        return False
    # Only approved facts earn win credit; one rejected since the draft was written gets none.
    approved_ids = [str(fid) for fid in (await db.execute(
        select(Fact.id).where(
            Fact.id.in_([str(x) for x in letter.fact_ids_used]),
            Fact.user_id == proposal.user_id,
            Fact.status == "approved",
        )
    )).scalars()]

    stamp = datetime.now(timezone.utc)
    claimed = (await db.execute(
        update(Proposal)
        .where(Proposal.id == proposal.id, Proposal.facts_credited_at.is_(None))
        .values(facts_credited_at=stamp)
        .returning(Proposal.id)
        .execution_options(synchronize_session=False)
    )).scalar_one_or_none()
    if claimed is None:
        return False
    proposal.facts_credited_at = stamp
    if approved_ids:
        await credit_facts(db, approved_ids, won=True, user_id=proposal.user_id)
    return True
