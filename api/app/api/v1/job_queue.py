"""Job queue endpoints — agent-discovered jobs awaiting user review.

Routes:
  POST   /api/v1/job-queue              — add a job to the queue (agent or manual)
  GET    /api/v1/job-queue              — list queued jobs for current user
  PUT    /api/v1/job-queue/{id}/action  — approve or reject a queued job
  GET    /api/v1/job-queue/stats        — learning summary (last 30 decisions)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.job_queue import JobQueueItem
from app.models.outcome_event import OutcomeEvent
from app.models.user import User
from app.schemas.job_queue import (
    JobQueueActionRequest,
    JobQueueCreate,
    JobQueueItemResponse,
)
from agent.autonomy_governor import (
    get_or_create_autonomy_profile,
    record_suggestion_approved,
    record_suggestion_rejected,
)

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_STATUSES = {"suggested", "approved", "rejected", "applied", "expired"}
VALID_ACTIONS = {"approve", "reject"}


def _to_response(item: JobQueueItem) -> JobQueueItemResponse:
    return JobQueueItemResponse.model_validate(item)


async def _record_outcome(
    db: AsyncSession,
    user_id: str,
    job_queue_id: str,
    event_type: str,
    meta: Optional[dict] = None,
) -> None:
    """Insert one row into outcome_events."""
    event = OutcomeEvent(
        id=str(uuid4()),
        user_id=user_id,
        job_queue_id=job_queue_id,
        event_type=event_type,
        meta=meta,
    )
    db.add(event)
    await db.flush()


# ── POST /api/v1/job-queue ─────────────────────────────────────────────────

@router.post("", response_model=JobQueueItemResponse, status_code=status.HTTP_201_CREATED)
async def create_job_queue_item(
    data: JobQueueCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a discovered job to the user's suggestion queue.

    Deduplicates by (user_id, upwork_url) — returns the existing item if the
    job is already in the queue.
    """
    # Deduplicate
    result = await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.user_id == current_user.id,
            JobQueueItem.upwork_url == data.upwork_url,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return _to_response(existing)

    item = JobQueueItem(
        id=str(uuid4()),
        user_id=current_user.id,
        upwork_url=data.upwork_url,
        title=data.title,
        description=data.description,
        skills=data.skills or [],
        budget_amount=data.budget_amount,
        budget_type=data.budget_type,
        client_info=data.client_info,
        ai_score=data.ai_score,
        ai_reasoning=data.ai_reasoning,
        chips=data.chips or [],
        status="suggested",
        source=data.source,
        source_query_id=data.source_query_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)

    # Record outcome event + increment suggestions_shown
    await _record_outcome(db, current_user.id, item.id, "suggested")
    ap = await get_or_create_autonomy_profile(current_user.id, db)
    ap.suggestions_shown += 1
    await db.flush()

    logger.info(
        "Added job_queue item %s for user %s (score=%.1f)",
        item.id, current_user.id, item.ai_score or 0,
    )
    return _to_response(item)


# ── GET /api/v1/job-queue/stats ────────────────────────────────────────────
# NOTE: /stats must be declared BEFORE /{item_id}/action to avoid route conflict.

@router.get("/stats", response_model=Dict[str, Any])
async def get_queue_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a learning summary for the current user.

    Includes autonomy level, score threshold, approval rate (last 30),
    all-time counts, and top rejection reasons.
    """
    ap = await get_or_create_autonomy_profile(current_user.id, db)

    # Approval rate from last 30 reviewed items
    recent_result = await db.execute(
        select(JobQueueItem)
        .where(
            JobQueueItem.user_id == current_user.id,
            JobQueueItem.status.in_(["approved", "rejected"]),
        )
        .order_by(JobQueueItem.reviewed_at.desc())
        .limit(30)
    )
    recent_items = recent_result.scalars().all()
    recent_approved = sum(1 for i in recent_items if i.status == "approved")
    recent_total = len(recent_items)
    recent_rate = (recent_approved / recent_total) if recent_total > 0 else None

    # Top rejection reasons
    reasons_result = await db.execute(
        select(JobQueueItem.rejection_reason, func.count().label("cnt"))
        .where(
            JobQueueItem.user_id == current_user.id,
            JobQueueItem.status == "rejected",
            JobQueueItem.rejection_reason.isnot(None),
        )
        .group_by(JobQueueItem.rejection_reason)
        .order_by(func.count().desc())
        .limit(5)
    )
    top_reasons = [
        {"reason": r, "count": c} for r, c in reasons_result.fetchall()
    ]

    level_labels = {
        1: "Observer", 2: "Suggester", 3: "Drafter",
        4: "Assisted", 5: "Autonomous", 6: "Optimizing",
    }

    return {
        "autonomy_level": ap.level,
        "autonomy_label": level_labels.get(ap.level, f"Level {ap.level}"),
        "level_since": ap.level_since.isoformat() if ap.level_since else None,
        "score_threshold": ap.score_threshold,
        "all_time": {
            "suggestions_shown": ap.suggestions_shown,
            "suggestions_approved": ap.suggestions_approved,
            "approval_rate": round(ap.approval_rate, 3),
        },
        "recent_30": {
            "total": recent_total,
            "approved": recent_approved,
            "approval_rate": round(recent_rate, 3) if recent_rate is not None else None,
        },
        "top_rejection_reasons": top_reasons,
    }


# ── GET /api/v1/job-queue ──────────────────────────────────────────────────

@router.get("", response_model=List[JobQueueItemResponse])
async def list_job_queue(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's job queue, newest first.

    Optional ?status= filter accepts any single status value or comma-separated list.
    """
    stmt = (
        select(JobQueueItem)
        .where(JobQueueItem.user_id == current_user.id)
        .order_by(JobQueueItem.created_at.desc())
        .limit(limit)
    )

    if status_filter:
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        invalid = set(statuses) - VALID_STATUSES
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status values: {invalid}. Valid: {VALID_STATUSES}",
            )
        stmt = stmt.where(JobQueueItem.status.in_(statuses))

    result = await db.execute(stmt)
    items = result.scalars().all()
    return [_to_response(item) for item in items]


# ── PUT /api/v1/job-queue/{id}/action ─────────────────────────────────────

@router.put("/{item_id}/action", response_model=JobQueueItemResponse)
async def action_job_queue_item(
    item_id: str,
    body: JobQueueActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a queued job.

    action: "approve" → status becomes "approved"
    action: "reject"  → status becomes "rejected"; rejection_reason stored

    Side effects:
    - Inserts an outcome_event row
    - Updates user_autonomy_profiles counters
    - Re-evaluates autonomy level and score threshold
    """
    if body.action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid action '{body.action}'. Valid: {VALID_ACTIONS}",
        )

    result = await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.id == item_id,
            JobQueueItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found.")

    if body.action == "approve":
        item.status = "approved"
        await _record_outcome(db, current_user.id, item_id, "approved")
        level_change = await record_suggestion_approved(current_user.id, db)
    else:
        item.status = "rejected"
        item.rejection_reason = body.rejection_reason
        meta = {"rejection_reason": body.rejection_reason} if body.rejection_reason else None
        await _record_outcome(db, current_user.id, item_id, "rejected", meta)
        level_change = await record_suggestion_rejected(current_user.id, db)

    item.reviewed_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(item)

    if level_change["level_before"] != level_change["level_after"]:
        logger.info(
            "User %s autonomy: Level %d → %d",
            current_user.id, level_change["level_before"], level_change["level_after"],
        )

    logger.info(
        "Job queue item %s → %s by user %s (threshold=%.1f)",
        item_id, item.status, current_user.id, level_change["threshold_after"],
    )
    return _to_response(item)
