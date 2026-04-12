"""Admin endpoints — platform-level stats (admin only).

Routes:
  GET /api/v1/admin/platform-stats — aggregate platform metrics
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.global_signal_pool import GlobalSignalPool
from app.models.job_queue import JobQueueItem
from app.models.outcome_event import OutcomeEvent
from app.models.user import User
from app.models.user_autonomy_profile import UserAutonomyProfile

logger = logging.getLogger(__name__)
router = APIRouter()

# Admin emails — in production this would be a DB role or env var
ADMIN_EMAILS = {"chris@servicevision.net"}


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.email not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


@router.get("/platform-stats")
async def get_platform_stats(
    _admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return platform-wide aggregate metrics (admin only).

    Includes user counts, autonomy level distribution, signal pool size,
    and 30-day engagement funnel.
    """
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Total users with autonomy profiles
    user_count_result = await db.execute(
        select(func.count()).select_from(UserAutonomyProfile)
    )
    total_users: int = user_count_result.scalar() or 0

    # Level distribution
    level_dist_result = await db.execute(
        select(
            UserAutonomyProfile.level,
            func.count().label("cnt"),
        ).group_by(UserAutonomyProfile.level).order_by(UserAutonomyProfile.level)
    )
    level_distribution = {
        row.level: row.cnt for row in level_dist_result.fetchall()
    }

    # Signal pool size and outcome distribution
    signal_count_result = await db.execute(
        select(func.count()).select_from(GlobalSignalPool)
    )
    signal_count: int = signal_count_result.scalar() or 0

    signal_outcomes_result = await db.execute(
        select(
            GlobalSignalPool.outcome_code,
            func.count().label("cnt"),
        ).group_by(GlobalSignalPool.outcome_code).order_by(func.count().desc())
    )
    signal_outcomes = {
        row.outcome_code: row.cnt for row in signal_outcomes_result.fetchall()
    }

    # Distinct skill hashes in pool
    skill_hash_count_result = await db.execute(
        select(func.count(GlobalSignalPool.skill_hash.distinct()))
    )
    distinct_skill_hashes: int = skill_hash_count_result.scalar() or 0

    # 30-day funnel: suggested → approved → submitted → responded
    funnel_result = await db.execute(
        select(
            OutcomeEvent.event_type,
            func.count().label("cnt"),
        ).where(
            OutcomeEvent.created_at >= thirty_days_ago,
        ).group_by(OutcomeEvent.event_type)
    )
    funnel_counts = {
        row.event_type: row.cnt for row in funnel_result.fetchall()
    }

    # Platform response rate (last 30 days)
    confirmed_30d = funnel_counts.get("confirmed_submit", 0)
    responded_30d = sum(
        funnel_counts.get(t, 0) for t in ("responded", "invited", "hired")
    )
    platform_response_rate = (
        round(responded_30d / confirmed_30d, 3) if confirmed_30d > 0 else None
    )

    # Active users last 7 days (had at least one outcome event)
    active_7d_result = await db.execute(
        select(func.count(OutcomeEvent.user_id.distinct()))
        .where(OutcomeEvent.created_at >= (now - timedelta(days=7)))
    )
    active_users_7d: int = active_7d_result.scalar() or 0

    return {
        "generated_at": now.isoformat(),
        "users": {
            "total_with_autonomy_profile": total_users,
            "active_last_7d": active_users_7d,
            "level_distribution": level_distribution,
        },
        "signal_pool": {
            "total_signals": signal_count,
            "distinct_skill_buckets": distinct_skill_hashes,
            "outcome_distribution": signal_outcomes,
        },
        "funnel_30d": {
            **funnel_counts,
            "platform_response_rate": platform_response_rate,
        },
    }
