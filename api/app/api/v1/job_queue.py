"""Job queue endpoints — agent-discovered jobs awaiting user review.

Routes:
  POST   /api/v1/job-queue          — add a job to the queue (agent or manual)
  GET    /api/v1/job-queue          — list queued jobs for current user
  PUT    /api/v1/job-queue/{id}/action — approve or reject a queued job
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.job_queue import JobQueueItem
from app.models.user import User
from app.schemas.job_queue import (
    JobQueueActionRequest,
    JobQueueCreate,
    JobQueueItemResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_STATUSES = {"suggested", "approved", "rejected", "applied", "expired"}
VALID_ACTIONS = {"approve", "reject"}


def _to_response(item: JobQueueItem) -> JobQueueItemResponse:
    return JobQueueItemResponse.model_validate(item)


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
    # Check for existing entry
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
        # 7-day TTL
        expires_at=datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).replace(hour=datetime.now(timezone.utc).hour,
                  minute=datetime.now(timezone.utc).minute,
                  second=datetime.now(timezone.utc).second),
    )
    # Set expires_at properly
    from datetime import timedelta
    item.expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    db.add(item)
    await db.flush()
    await db.refresh(item)
    logger.info("Added job_queue item %s for user %s (score=%.1f)", item.id, current_user.id, item.ai_score or 0)
    return _to_response(item)


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
    Defaults to returning all non-expired items.
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
    else:
        item.status = "rejected"
        item.rejection_reason = body.rejection_reason

    item.reviewed_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(item)
    logger.info("Job queue item %s → %s by user %s", item_id, item.status, current_user.id)
    return _to_response(item)
