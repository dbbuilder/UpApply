"""Daily digest builder — summarizes agent activity for a user.

Produces a structured dict suitable for:
  - GET /api/v1/agent/digest (JSON for the extension)
  - Future email delivery via digest_email

Digest sections:
  - autonomy: current level, score threshold, days at this level
  - today: jobs discovered, prepped autonomously, submitted, responses received
  - pipeline: pending review, drafts ready, awaiting response
  - learning: approval rate trend, edit distance trend, response rate
  - roi: connects invested, estimated value (responses × avg_rate)
  - recent_activity: last 10 outcome events with human-readable labels
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_queue import JobQueueItem
from app.models.outcome_event import OutcomeEvent
from app.models.user_autonomy_profile import UserAutonomyProfile
from app.models.user_guardrail_config import UserGuardrailConfig

logger = logging.getLogger(__name__)

LEVEL_LABELS = {
    1: "Observer",
    2: "Suggester",
    3: "Drafter",
    4: "Assisted",
    5: "Autonomous",
    6: "Optimizing",
}

EVENT_LABELS = {
    "suggested": "Job surfaced",
    "approved": "Job approved",
    "rejected": "Job rejected",
    "proposal_drafted": "Draft generated",
    "proposal_submitted": "Cover letter sent",
    "confirmed_submit": "Submission confirmed",
    "viewed": "Proposal viewed by client",
    "responded": "Client responded",
    "invited": "Client invited for interview",
    "declined": "Proposal declined",
    "hired": "Hired!",
}


async def build_digest(user_id: str, db: AsyncSession) -> Dict[str, Any]:
    """Build a full digest for one user. Returns a dict.

    All queries run against the same session; caller is responsible for
    committing or rolling back.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)

    # ── Autonomy profile ──────────────────────────────────────────────────────

    ap_result = await db.execute(
        select(UserAutonomyProfile).where(UserAutonomyProfile.user_id == user_id)
    )
    ap: Optional[UserAutonomyProfile] = ap_result.scalar_one_or_none()

    if ap is None:
        return {"error": "No autonomy profile found — run job discovery first."}

    days_at_level = (now - ap.level_since).days if ap.level_since else 0

    # Next level unlock hints
    next_level_hint = _next_level_hint(ap)

    # ── Guardrail config ──────────────────────────────────────────────────────

    gc_result = await db.execute(
        select(UserGuardrailConfig).where(UserGuardrailConfig.user_id == user_id)
    )
    gc: Optional[UserGuardrailConfig] = gc_result.scalar_one_or_none()

    # ── Today's activity ──────────────────────────────────────────────────────

    today_events_result = await db.execute(
        select(OutcomeEvent.event_type, func.count().label("cnt"))
        .where(
            OutcomeEvent.user_id == user_id,
            OutcomeEvent.created_at >= today_start,
        )
        .group_by(OutcomeEvent.event_type)
    )
    today_counts: Dict[str, int] = {
        row.event_type: row.cnt for row in today_events_result.fetchall()
    }

    # ── Pipeline state ────────────────────────────────────────────────────────

    pipeline_result = await db.execute(
        select(JobQueueItem.status, JobQueueItem.draft_status, func.count().label("cnt"))
        .where(
            JobQueueItem.user_id == user_id,
            JobQueueItem.expires_at > now,
        )
        .group_by(JobQueueItem.status, JobQueueItem.draft_status)
    )
    pipeline_rows = pipeline_result.fetchall()

    pending_review = sum(r.cnt for r in pipeline_rows if r.status == "suggested")
    drafts_ready = sum(r.cnt for r in pipeline_rows if r.draft_status == "ready")
    awaiting_response = sum(
        r.cnt for r in pipeline_rows
        if r.status == "applied" and r.draft_status == "sent"
    )

    # ── ROI metrics ───────────────────────────────────────────────────────────

    # Connects invested (last 30 days)
    connects_result = await db.execute(
        select(func.sum(JobQueueItem.connects_spent))
        .where(
            JobQueueItem.user_id == user_id,
            JobQueueItem.confirmed_at >= (now - timedelta(days=30)),
            JobQueueItem.connects_spent.isnot(None),
        )
    )
    connects_30d: int = connects_result.scalar() or 0

    # Response rate (last 30 days)
    submitted_30d_result = await db.execute(
        select(func.count())
        .where(
            JobQueueItem.user_id == user_id,
            JobQueueItem.confirmed_at >= (now - timedelta(days=30)),
        )
    )
    submitted_30d: int = submitted_30d_result.scalar() or 0

    responded_30d_result = await db.execute(
        select(func.count())
        .where(
            JobQueueItem.user_id == user_id,
            JobQueueItem.client_response_at >= (now - timedelta(days=30)),
            JobQueueItem.client_response_type.in_(["responded", "invited"]),
        )
    )
    responded_30d: int = responded_30d_result.scalar() or 0

    response_rate_30d = (responded_30d / submitted_30d) if submitted_30d > 0 else None

    # ── Recent activity (last 10 events) ─────────────────────────────────────

    recent_events_result = await db.execute(
        select(OutcomeEvent)
        .where(OutcomeEvent.user_id == user_id)
        .order_by(OutcomeEvent.created_at.desc())
        .limit(10)
    )
    recent_events = recent_events_result.scalars().all()

    recent_activity = []
    for evt in recent_events:
        # Fetch job title if available
        job_title = None
        if evt.job_queue_id:
            jq_result = await db.execute(
                select(JobQueueItem.title).where(JobQueueItem.id == evt.job_queue_id)
            )
            title_row = jq_result.first()
            if title_row:
                job_title = title_row[0][:60]

        recent_activity.append({
            "event": EVENT_LABELS.get(evt.event_type, evt.event_type),
            "job_title": job_title,
            "at": evt.created_at.isoformat(),
        })

    # ── Assemble ──────────────────────────────────────────────────────────────

    digest = {
        "generated_at": now.isoformat(),
        "autonomy": {
            "level": ap.level,
            "label": LEVEL_LABELS.get(ap.level, f"Level {ap.level}"),
            "days_at_level": days_at_level,
            "score_threshold": ap.score_threshold,
            "next_level_hint": next_level_hint,
            "locked": ap.locked,
        },
        "today": {
            "surfaced": today_counts.get("suggested", 0),
            "approved": today_counts.get("approved", 0),
            "rejected": today_counts.get("rejected", 0),
            "drafted": today_counts.get("proposal_drafted", 0),
            "submitted": today_counts.get("confirmed_submit", 0),
            "responses": sum(
                today_counts.get(t, 0) for t in ("responded", "invited", "hired")
            ),
        },
        "pipeline": {
            "pending_review": pending_review,
            "drafts_ready": drafts_ready,
            "awaiting_response": awaiting_response,
        },
        "learning": {
            "approval_rate": round(ap.approval_rate, 3),
            "avg_edit_distance": ap.avg_edit_distance,
            "response_rate": ap.response_rate,
            "all_time_submitted": ap.proposals_submitted,
            "all_time_responded": ap.proposals_responded,
        },
        "roi_30d": {
            "connects_invested": connects_30d,
            "submissions": submitted_30d,
            "responses": responded_30d,
            "response_rate": round(response_rate_30d, 3) if response_rate_30d is not None else None,
            "connects_balance": gc.connects_balance if gc else None,
            "min_reserve": gc.min_connects_reserve if gc else None,
        },
        "recent_activity": recent_activity,
    }

    logger.debug("Digest built for user %s", user_id)
    return digest


def _next_level_hint(ap: UserAutonomyProfile) -> Optional[str]:
    """Return a human-readable hint for what's needed to reach the next level."""
    level = ap.level
    if level == 1:
        needed = max(0, 10 - ap.suggestions_shown)
        return f"See {needed} more job suggestions to advance" if needed > 0 else "Ready to advance — approval rate needs 60%+ over 20 suggestions"
    if level == 2:
        rate_pct = round(ap.approval_rate * 100, 1)
        needed = max(0, 20 - ap.suggestions_shown)
        if needed > 0:
            return f"Review {needed} more suggestions (need 20 total, currently {ap.suggestions_shown})"
        if ap.approval_rate < 0.60:
            return f"Approval rate {rate_pct}% needs to reach 60% — keep approving quality jobs"
        return "Requirements met — level up pending next evaluation"
    if level == 3:
        ed = ap.avg_edit_distance
        needed_drafts = max(0, 10 - ap.proposals_submitted)
        if needed_drafts > 0:
            return f"Submit {needed_drafts} more proposals using AI drafts"
        if ed is None or ed > 0.15:
            ed_pct = f"{(ed or 0) * 100:.1f}%"
            return f"Edit distance {ed_pct} needs to reach ≤15% — use AI drafts more as-is"
        return "Requirements met — level up pending next evaluation"
    if level == 4:
        rr_pct = round(ap.response_rate * 100, 1)
        needed_subs = max(0, 20 - ap.proposals_submitted)
        if needed_subs > 0:
            return f"Submit {needed_subs} more proposals (need 20 total)"
        if ap.response_rate < 0.25:
            return f"Response rate {rr_pct}% needs to reach 25% — keep refining job targeting"
        return "Requirements met — level up pending next evaluation"
    if level == 5:
        return "Level 6 (Optimizing) requires manual opt-in from settings"
    return None
