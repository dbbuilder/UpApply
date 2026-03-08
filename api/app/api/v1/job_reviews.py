"""Job review endpoints — scored job ratings for self-improvement."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.job_review import JobReview
from app.schemas.job_review import JobReviewUpsert, JobReviewRate, JobReviewResponse, JobReviewListResponse

router = APIRouter()


@router.post("", response_model=JobReviewResponse, status_code=status.HTTP_200_OK)
async def upsert_job_review(
    data: JobReviewUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upsert a job review record when a job is scored. Idempotent by URL."""
    result = await db.execute(
        select(JobReview).where(
            JobReview.user_id == current_user.id,
            JobReview.upwork_job_url == data.upwork_job_url,
        )
    )
    review = result.scalar_one_or_none()

    if review:
        review.ai_score = data.ai_score
        review.chips = data.chips
        review.budget_amount = data.budget_amount
        review.budget_type = data.budget_type
        review.scored_at = data.scored_at or datetime.now(timezone.utc)
        if data.upwork_job_id:
            review.upwork_job_id = data.upwork_job_id
    else:
        review = JobReview(
            user_id=current_user.id,
            upwork_job_url=data.upwork_job_url,
            upwork_job_id=data.upwork_job_id,
            job_title=data.job_title,
            ai_score=data.ai_score,
            chips=data.chips,
            budget_amount=data.budget_amount,
            budget_type=data.budget_type,
            scored_at=data.scored_at or datetime.now(timezone.utc),
        )
        db.add(review)

    await db.commit()
    await db.refresh(review)
    return review


@router.patch("/{review_id}/rate", response_model=JobReviewResponse)
async def rate_job_review(
    review_id: str,
    data: JobReviewRate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set user rating (1–5) and optional comment on a scored job."""
    result = await db.execute(
        select(JobReview).where(
            JobReview.id == review_id,
            JobReview.user_id == current_user.id,
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")

    review.user_rating = data.user_rating
    review.user_comment = data.user_comment
    await db.commit()
    await db.refresh(review)
    return review


@router.get("", response_model=JobReviewListResponse)
async def list_job_reviews(
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    chip: Optional[List[str]] = None,
    has_rating: Optional[bool] = None,
    sort: str = "score",  # score | recent | rating
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List scored job reviews with optional filters."""
    query = select(JobReview).where(JobReview.user_id == current_user.id)

    if min_score is not None:
        query = query.where(JobReview.ai_score >= min_score)
    if max_score is not None:
        query = query.where(JobReview.ai_score <= max_score)
    if has_rating is True:
        query = query.where(JobReview.user_rating.is_not(None))
    elif has_rating is False:
        query = query.where(JobReview.user_rating.is_(None))

    if sort == "recent":
        query = query.order_by(JobReview.scored_at.desc().nullslast())
    elif sort == "rating":
        query = query.order_by(JobReview.user_rating.desc().nullslast(), JobReview.ai_score.desc().nullslast())
    else:  # score
        query = query.order_by(JobReview.ai_score.desc().nullslast())

    count_result = await db.execute(select(JobReview).where(JobReview.user_id == current_user.id))
    total = len(count_result.scalars().all())

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    reviews = result.scalars().all()

    # Post-filter by chip (JSON contains any of the requested chips)
    if chip:
        reviews = [r for r in reviews if r.chips and any(c in r.chips for c in chip)]

    return JobReviewListResponse(reviews=list(reviews), total=total)


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_review(
    review_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a job review from the list."""
    result = await db.execute(
        select(JobReview).where(
            JobReview.id == review_id,
            JobReview.user_id == current_user.id,
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    await db.delete(review)
    await db.commit()
