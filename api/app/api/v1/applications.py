"""Application endpoints for tracking job applications."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.job import Job
from app.models.application import Application, ApplicationStatus
from app.schemas.application import (
    ApplicationCreate,
    ApplicationUpdate,
    ApplicationOutcome,
    ApplicationResponse,
    ApplicationStats,
)

router = APIRouter()


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    application_data: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new application record."""
    # Verify job exists and belongs to user
    result = await db.execute(
        select(Job).where(
            Job.id == application_data.job_id,
            Job.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Check if application already exists
    result = await db.execute(
        select(Application).where(
            Application.job_id == application_data.job_id,
            Application.user_id == current_user.id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Application already exists for this job",
        )

    application = Application(
        user_id=current_user.id,
        job_id=application_data.job_id,
        cover_letter_id=application_data.cover_letter_id,
        bid_amount=application_data.bid_amount,
        status=application_data.status,
    )

    db.add(application)
    await db.commit()
    await db.refresh(application)

    return application


@router.get("", response_model=List[ApplicationResponse])
async def list_applications(
    status_filter: Optional[ApplicationStatus] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's applications."""
    query = select(Application).where(Application.user_id == current_user.id)

    if status_filter:
        query = query.where(Application.status == status_filter)

    query = query.order_by(Application.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    applications = result.scalars().all()

    return applications


@router.get("/stats", response_model=ApplicationStats)
async def get_application_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get application statistics."""
    # Get all applications
    result = await db.execute(
        select(Application).where(Application.user_id == current_user.id)
    )
    applications = result.scalars().all()

    total = len(applications)
    if total == 0:
        return ApplicationStats(
            total_applications=0,
            submitted=0,
            viewed=0,
            responded=0,
            hired=0,
            declined=0,
            response_rate=0.0,
            success_rate=0.0,
            total_earnings=0.0,
        )

    # Count by status
    submitted = sum(1 for a in applications if a.status != ApplicationStatus.DRAFT)
    viewed = sum(1 for a in applications if a.status in [
        ApplicationStatus.VIEWED,
        ApplicationStatus.RESPONDED,
        ApplicationStatus.INTERVIEWED,
        ApplicationStatus.HIRED,
        ApplicationStatus.DECLINED,
    ])
    responded = sum(1 for a in applications if a.status in [
        ApplicationStatus.RESPONDED,
        ApplicationStatus.INTERVIEWED,
        ApplicationStatus.HIRED,
    ])
    hired = sum(1 for a in applications if a.status == ApplicationStatus.HIRED)
    declined = sum(1 for a in applications if a.status == ApplicationStatus.DECLINED)

    # Calculate rates
    response_rate = (responded / submitted * 100) if submitted > 0 else 0.0
    success_rate = (hired / submitted * 100) if submitted > 0 else 0.0

    # Total earnings
    total_earnings = sum(a.earnings or 0 for a in applications)

    # Average match score from associated jobs
    job_ids = [a.job_id for a in applications]
    if job_ids:
        result = await db.execute(
            select(func.avg(Job.match_score)).where(Job.id.in_(job_ids))
        )
        avg_match_score = result.scalar()
    else:
        avg_match_score = None

    return ApplicationStats(
        total_applications=total,
        submitted=submitted,
        viewed=viewed,
        responded=responded,
        hired=hired,
        declined=declined,
        response_rate=round(response_rate, 1),
        success_rate=round(success_rate, 1),
        total_earnings=total_earnings,
        avg_match_score=round(avg_match_score, 1) if avg_match_score else None,
    )


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific application."""
    result = await db.execute(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == current_user.id,
        )
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    return application


@router.put("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: str,
    update_data: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an application."""
    result = await db.execute(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == current_user.id,
        )
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    update_dict = update_data.model_dump(exclude_unset=True)

    for field, value in update_dict.items():
        setattr(application, field, value)

    # Track submission time
    if update_data.status == ApplicationStatus.SUBMITTED and not application.submitted_at:
        application.submitted_at = datetime.utcnow()

    await db.commit()
    await db.refresh(application)

    return application


@router.put("/{application_id}/outcome", response_model=ApplicationResponse)
async def record_outcome(
    application_id: str,
    outcome: ApplicationOutcome,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record application outcome (hired, declined, etc.)."""
    result = await db.execute(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == current_user.id,
        )
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    application.status = outcome.status
    application.outcome_notes = outcome.outcome_notes
    application.client_response = outcome.client_response
    application.outcome_recorded_at = datetime.utcnow()

    if outcome.earnings:
        application.earnings = outcome.earnings

    # Track response time
    if outcome.status in [
        ApplicationStatus.RESPONDED,
        ApplicationStatus.INTERVIEWED,
        ApplicationStatus.HIRED,
    ] and not application.responded_at:
        application.responded_at = datetime.utcnow()

    await db.commit()
    await db.refresh(application)

    return application


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an application."""
    result = await db.execute(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == current_user.id,
        )
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    await db.delete(application)
    await db.commit()
