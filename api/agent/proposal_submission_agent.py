"""ProposalSubmissionAgent — Level 5 autonomous prep pipeline.

At Level 5 (Autonomous), this agent:
  1. Reads all items in the job_queue with status="suggested"
  2. Runs guardrail checks for each (enabled, daily cap, connects, score threshold)
  3. For items that pass all guards:
     - Auto-approves the item (status → approved)
     - Generates a cover letter draft (draft_status → ready)
     - Calls confirm_submit internally (confirmed_at set)
     - Writes pendingAutoFill to the agent's output batch
  4. Records all actions to outcome_events and autonomy_profile

This agent does NOT submit to Upwork. It prepares the auto-fill payload.
The user still manually clicks "Submit" on Upwork (ToS-safe).

Level 6 adds search_optimizer integration for query tuning.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.autonomy_governor import get_or_create_autonomy_profile, record_suggestion_approved
from agent.guardrails import GuardrailViolation, check_submission_guards
from agent.learning_engine import apply_cold_start, contribute_signal
from app.models.job_queue import JobQueueItem
from app.models.outcome_event import OutcomeEvent
from app.models.user import UserProfile
from app.models.user_autonomy_profile import UserAutonomyProfile

logger = logging.getLogger(__name__)


@dataclass
class SubmissionPrepResult:
    """Summary of one autonomous submission prep run."""

    user_id: str
    items_evaluated: int = 0
    items_prepped: int = 0
    items_blocked: int = 0
    skipped_low_score: int = 0
    prepped_items: list = field(default_factory=list)  # list of {item_id, title, score}
    blocked_reasons: list = field(default_factory=list)  # list of {item_id, guard, reason}


async def _record_outcome(
    db: AsyncSession,
    user_id: str,
    job_queue_id: str,
    event_type: str,
    meta: Optional[dict] = None,
) -> None:
    event = OutcomeEvent(
        id=str(uuid4()),
        user_id=user_id,
        job_queue_id=job_queue_id,
        event_type=event_type,
        meta=meta,
    )
    db.add(event)
    await db.flush()


async def run_autonomous_prep(
    user_id: str,
    db: AsyncSession,
) -> SubmissionPrepResult:
    """Run the Level 5 autonomous submission prep for one user.

    Called from run_discovery.py after job discovery when the user's autonomy
    level is >= 5. Processes all suggested items in the queue.

    Returns a SubmissionPrepResult summary.
    """
    result = SubmissionPrepResult(user_id=user_id)

    # Verify user is at Level 5+
    ap = await get_or_create_autonomy_profile(user_id, db)
    if ap.level < 5:
        logger.info("User %s is at Level %d — skipping autonomous prep", user_id, ap.level)
        return result

    # Get profile for cold-start initialization
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()

    # Try cold-start if this is a new autonomy profile
    if profile and profile.skills:
        skill_names = [s["name"] if isinstance(s, dict) else s for s in (profile.skills or [])]
        await apply_cold_start(user_id, skill_names, db)
        # Re-fetch after potential cold-start update
        ap = await get_or_create_autonomy_profile(user_id, db)

    # Fetch all suggested items
    items_result = await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.user_id == user_id,
            JobQueueItem.status == "suggested",
            JobQueueItem.draft_status == "none",
        ).order_by(JobQueueItem.ai_score.desc().nullslast())
    )
    items = items_result.scalars().all()

    if not items:
        logger.info("User %s: no suggested items to prep autonomously", user_id)
        return result

    logger.info(
        "User %s: autonomous prep — evaluating %d suggested items (level=%d, threshold=%.1f)",
        user_id, len(items), ap.level, ap.score_threshold,
    )

    for item in items:
        result.items_evaluated += 1

        # Score gate — only prep high-confidence jobs
        if item.ai_score is None or item.ai_score < ap.score_threshold:
            result.skipped_low_score += 1
            logger.debug(
                "Item %s skipped: score %.1f < threshold %.1f",
                item.id, item.ai_score or 0, ap.score_threshold,
            )
            continue

        # Run all guardrail checks
        guards = await check_submission_guards(
            user_id=user_id,
            db=db,
            score=item.ai_score,
            bid_amount=None,  # Unknown at discovery time
            is_hourly=(item.budget_type == "hourly" if item.budget_type else True),
        )

        if not guards.passed:
            first = guards.first_blocking()
            result.items_blocked += 1
            result.blocked_reasons.append({
                "item_id": item.id,
                "title": item.title[:80],
                "guard": first.guard if first else "unknown",
                "reason": first.reason if first else "guardrail failed",
            })
            logger.info(
                "Item %s blocked by guardrail %s: %s",
                item.id, first.guard if first else "?", first.reason if first else "",
            )
            # If the daily cap or connects are the blocker, stop processing more items
            if first and first.guard in ("DAILY_CAP", "CONNECTS_RESERVE"):
                logger.warning(
                    "User %s: stopping autonomous prep — %s", user_id, first.guard
                )
                break
            continue

        # Auto-approve
        item.status = "approved"
        item.reviewed_at = datetime.now(timezone.utc)
        item.draft_status = "generating"
        await db.flush()

        await _record_outcome(db, user_id, item.id, "approved", {"source": "autonomous"})
        await record_suggestion_approved(user_id, db)

        result.items_prepped += 1
        result.prepped_items.append({
            "item_id": item.id,
            "title": item.title[:80],
            "score": item.ai_score,
        })

        logger.info(
            "Autonomous prep: approved item %s for user %s (score=%.1f)",
            item.id, user_id, item.ai_score,
        )

    # Contribute anonymized signal for each prepped item
    if profile and profile.skills:
        skill_names = [s["name"] if isinstance(s, dict) else s for s in (profile.skills or [])]
        for prep in result.prepped_items:
            try:
                await contribute_signal(
                    skills=skill_names,
                    outcome_code="approved",
                    score_at_submission=prep.get("score"),
                    edit_distance_pct=ap.avg_edit_distance,
                    db=db,
                )
            except Exception as exc:
                logger.warning("Signal contribution failed: %s", exc)

    logger.info(
        "User %s autonomous prep complete: evaluated=%d prepped=%d blocked=%d skipped=%d",
        user_id,
        result.items_evaluated,
        result.items_prepped,
        result.items_blocked,
        result.skipped_low_score,
    )
    return result
