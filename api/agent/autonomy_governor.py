"""AutonomyGovernor — evaluates and advances (or downgrades) user autonomy levels.

Called:
  1. After each approve/reject action (lightweight check)
  2. Daily by run_discovery.py cron (full evaluation for all users)

Level progression thresholds:
  1 Observer  → 2 Suggester  : suggestions_shown >= 10
  2 Suggester → 3 Drafter    : approval_rate >= 0.60 AND suggestions_shown >= 20
  3 Drafter   → 4 Assisted   : avg_edit_distance <= 15.0 AND proposals_drafted >= 10
  4 Assisted  → 5 Autonomous : response_rate >= 0.25 AND proposals_submitted >= 20
  5 → 6 Optimizing           : manual opt-in only

Downgrade conditions (checked daily):
  Level 2 → 1 : approval_rate < 0.30 AND suggestions_shown >= 20
  Level 3 → 2 : avg_edit_distance > 40.0 AND proposals_drafted >= 5

Score threshold auto-adjustment:
  - approval_rate > 0.80 → lower threshold by 2 (show more, user is happy)
  - approval_rate < 0.40 → raise threshold by 3 (user is rejecting too much)
  - Clamped to [40.0, 80.0]
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user_autonomy_profile import UserAutonomyProfile

logger = logging.getLogger(__name__)

# ── Threshold constants ──────────────────────────────────────────────────────

UNLOCK_CONDITIONS: dict[int, dict] = {
    # current_level → what's needed to advance
    1: {"suggestions_shown": 10},
    2: {"approval_rate": 0.60, "suggestions_shown": 20},
    3: {"avg_edit_distance_lte": 15.0, "proposals_submitted": 10},
    4: {"response_rate": 0.25, "proposals_submitted": 20},
}

DOWNGRADE_CONDITIONS: dict[int, dict] = {
    # current_level → what triggers a downgrade
    2: {"approval_rate_lt": 0.30, "suggestions_shown_gte": 20},
    3: {"avg_edit_distance_gt": 40.0, "proposals_submitted_gte": 5},
}

SCORE_THRESHOLD_MIN = 40.0
SCORE_THRESHOLD_MAX = 80.0


# ── Core evaluation ──────────────────────────────────────────────────────────

def _check_unlock(ap: UserAutonomyProfile) -> bool:
    """Return True if ap's metrics meet the unlock conditions for the next level."""
    cond = UNLOCK_CONDITIONS.get(ap.level)
    if cond is None:
        return False  # Level 5 → 6 is manual only

    for key, threshold in cond.items():
        if key == "suggestions_shown":
            if ap.suggestions_shown < threshold:
                return False
        elif key == "approval_rate":
            if ap.approval_rate < threshold:
                return False
        elif key == "avg_edit_distance_lte":
            if ap.avg_edit_distance is None or ap.avg_edit_distance > threshold:
                return False
        elif key == "proposals_submitted":
            if ap.proposals_submitted < threshold:
                return False
        elif key == "response_rate":
            if ap.response_rate < threshold:
                return False
    return True


def _check_downgrade(ap: UserAutonomyProfile) -> bool:
    """Return True if ap's metrics trigger a downgrade."""
    cond = DOWNGRADE_CONDITIONS.get(ap.level)
    if cond is None:
        return False

    for key, threshold in cond.items():
        if key == "approval_rate_lt":
            if ap.approval_rate >= threshold:
                return False
        elif key == "suggestions_shown_gte":
            if ap.suggestions_shown < threshold:
                return False
        elif key == "avg_edit_distance_gt":
            if ap.avg_edit_distance is None or ap.avg_edit_distance <= threshold:
                return False
        elif key == "proposals_submitted_gte":
            if ap.proposals_submitted < threshold:
                return False
    return True


def _adjust_score_threshold(ap: UserAutonomyProfile) -> None:
    """Nudge score_threshold based on recent approval rate."""
    if ap.suggestions_shown < 10:
        return  # Not enough data

    rate = ap.approval_rate
    old = ap.score_threshold

    if rate > 0.80:
        ap.score_threshold = max(SCORE_THRESHOLD_MIN, old - 2.0)
    elif rate < 0.40:
        ap.score_threshold = min(SCORE_THRESHOLD_MAX, old + 3.0)

    if ap.score_threshold != old:
        logger.info(
            "User %s: score_threshold %.1f → %.1f (approval_rate=%.2f)",
            ap.user_id, old, ap.score_threshold, rate,
        )


# ── Public API ───────────────────────────────────────────────────────────────

async def evaluate_user(ap: UserAutonomyProfile, db: AsyncSession) -> dict:
    """Evaluate and potentially advance or downgrade a user's autonomy level.

    Returns a dict describing what changed:
      {"level_before": N, "level_after": N, "threshold_before": F, "threshold_after": F}
    """
    if ap.locked:
        logger.debug("User %s autonomy profile is locked — skipping evaluation", ap.user_id)
        return {"level_before": ap.level, "level_after": ap.level,
                "threshold_before": ap.score_threshold, "threshold_after": ap.score_threshold}

    level_before = ap.level
    threshold_before = ap.score_threshold

    # Level advancement (only one level per evaluation)
    if _check_unlock(ap):
        ap.level += 1
        ap.level_since = datetime.now(timezone.utc)
        logger.info("User %s: autonomy level %d → %d", ap.user_id, level_before, ap.level)

    # Downgrade check (only if we didn't just advance)
    elif _check_downgrade(ap):
        ap.level -= 1
        ap.level_since = datetime.now(timezone.utc)
        logger.info("User %s: autonomy level %d → %d (downgraded)", ap.user_id, level_before, ap.level)

    # Score threshold adjustment
    _adjust_score_threshold(ap)

    ap.last_evaluated = datetime.now(timezone.utc)
    await db.flush()

    return {
        "level_before": level_before,
        "level_after": ap.level,
        "threshold_before": threshold_before,
        "threshold_after": ap.score_threshold,
    }


async def get_or_create_autonomy_profile(
    user_id: str, db: AsyncSession
) -> UserAutonomyProfile:
    """Return the user's autonomy profile, creating it at Level 1 if missing."""
    result = await db.execute(
        select(UserAutonomyProfile).where(UserAutonomyProfile.user_id == user_id)
    )
    ap = result.scalar_one_or_none()
    if ap is None:
        ap = UserAutonomyProfile(user_id=user_id)
        db.add(ap)
        await db.flush()
        logger.info("Created autonomy profile for user %s at Level 1", user_id)
    return ap


async def record_suggestion_shown(user_id: str, db: AsyncSession) -> None:
    """Increment suggestions_shown counter (called when agent queues a job)."""
    ap = await get_or_create_autonomy_profile(user_id, db)
    ap.suggestions_shown += 1
    await db.flush()


async def record_suggestion_approved(user_id: str, db: AsyncSession) -> dict:
    """Increment suggestions_approved and re-evaluate level."""
    ap = await get_or_create_autonomy_profile(user_id, db)
    ap.suggestions_approved += 1
    return await evaluate_user(ap, db)


async def record_suggestion_rejected(user_id: str, db: AsyncSession) -> dict:
    """Re-evaluate level after a rejection (no counter increment — already shown)."""
    ap = await get_or_create_autonomy_profile(user_id, db)
    return await evaluate_user(ap, db)
