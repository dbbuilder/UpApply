"""Beta feedback endpoints for tester feedback collection."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.beta_feedback import BetaFeedback
from app.schemas.beta_feedback import (
    BetaFeedbackCreate,
    BetaFeedbackResponse,
    BetaFeedbackList,
)
from app.core.rate_limit import limiter

router = APIRouter()


@router.post("", response_model=BetaFeedbackResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def submit_beta_feedback(
    request: Request,
    feedback_data: BetaFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Submit beta feedback. No authentication required.

    This endpoint is for beta testers to report bugs, request features,
    or provide general feedback about the extension.
    """
    feedback = BetaFeedback(
        feedback_type=feedback_data.feedback_type,
        description=feedback_data.description,
        email=feedback_data.email,
        page_url=feedback_data.page_url,
        extension_version=feedback_data.extension_version,
        browser_info=feedback_data.browser_info,
        user_id=current_user.id if current_user else None,
    )

    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return feedback


@router.get("", response_model=BetaFeedbackList)
async def list_beta_feedback(
    feedback_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List beta feedback (requires authentication)."""
    query = select(BetaFeedback)

    if feedback_type:
        query = query.where(BetaFeedback.feedback_type == feedback_type)

    # Get total count
    count_query = select(func.count()).select_from(BetaFeedback)
    if feedback_type:
        count_query = count_query.where(BetaFeedback.feedback_type == feedback_type)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get items
    query = query.order_by(BetaFeedback.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    items = result.scalars().all()

    return BetaFeedbackList(items=items, total=total)
