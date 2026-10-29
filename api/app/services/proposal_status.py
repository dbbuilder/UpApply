"""Canonical proposal stages: one place that maps raw Upwork / client statuses to a stage.

proposals.status keeps the raw value; proposals.stage holds the canonical one and is set from
it whenever status is assigned (Proposal.status validator). Every stage change appends a row to
proposal_stage_events (see app.models.proposal_stage_event).

To extend: add the lowercased raw value to STAGE_ALIASES. Only map an Upwork numeric code once
its meaning is confirmed; anything unmapped is "unknown", never guessed.
"""
from typing import Optional

STAGES = ("submitted", "viewed", "replied", "interview", "hired", "declined", "closed", "unknown")
UNKNOWN = "unknown"

STAGE_ALIASES: dict[str, str] = {
    # Upwork numeric status codes (proposal detail page). Confirmed only.
    "7": "submitted",
    # Text: extension list scraper, outcome sync, sidebar, application statuses
    "submitted": "submitted",
    "viewed": "viewed",
    "responded": "replied",
    "replied": "replied",
    "interview": "interview",
    "interviewed": "interview",
    "hired": "hired",
    "declined": "declined",
    "archived": "closed",
    "closed": "closed",
    "withdrawn": "closed",
}

# Forward order for syncs: a sync only moves a proposal along this ranking, so a later scrape
# never drags a reply back to "submitted" (a reply is not overwritten by a decline either,
# matching outcomes._RANK).
_FORWARD_RANK = {
    UNKNOWN: 0, "submitted": 1, "viewed": 2, "closed": 3, "declined": 4,
    "replied": 5, "interview": 6, "hired": 7,
}


def stage_for(raw_status: Optional[str]) -> str:
    """Canonical stage for a raw status; unmapped or empty → "unknown"."""
    return STAGE_ALIASES.get((raw_status or "").strip().lower(), UNKNOWN)


def set_status(proposal, raw_status: Optional[str], source: str) -> None:
    """Write a raw status (stage follows) and name the ledger source for this change."""
    proposal._stage_source = source
    proposal.status = raw_status


def advance_status(proposal, raw_status: Optional[str], source: str) -> bool:
    """Write the status only when its stage moves the proposal forward. True if written."""
    new = stage_for(raw_status)
    if _FORWARD_RANK[new] <= _FORWARD_RANK.get(proposal.stage or UNKNOWN, 0):
        return False
    set_status(proposal, str(raw_status).strip()[:50], source)
    return True
