"""Application endpoints for tracking job applications."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.embeddings import generate_embedding
from app.models.user import User
from app.models.job import Job
from app.models.cover_letter import CoverLetter
from app.models.proposal import Proposal
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
        application.submitted_at = datetime.now(timezone.utc)

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
    application.outcome_recorded_at = datetime.now(timezone.utc)

    if outcome.earnings:
        application.earnings = outcome.earnings

    # Track response time
    if outcome.status in [
        ApplicationStatus.RESPONDED,
        ApplicationStatus.INTERVIEWED,
        ApplicationStatus.HIRED,
    ] and not application.responded_at:
        application.responded_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(application)

    # Auto-promote winning letter to the proposals corpus so future generation
    # can use it as a high-weight few-shot example.
    if outcome.status in [ApplicationStatus.HIRED, ApplicationStatus.OFFERED]:
        await _promote_winning_letter(db, application, current_user.id)

    return application


async def _promote_winning_letter(
    db: AsyncSession,
    application: Application,
    user_id: str,
) -> None:
    """Upsert the winning cover letter into the proposals corpus (was_hired=True).

    Uses submitted_text if available (captured when user clicked 'Mark as Submitted'),
    otherwise falls back to the generated content.  Idempotent — safe to call
    multiple times for the same application.
    """
    try:
        # Resolve the text to promote
        letter_text: Optional[str] = None
        job_title: Optional[str] = None
        job_skills: Optional[list] = None

        # Load cover letter (may be linked or may need to be found by job_id)
        if application.cover_letter_id:
            cl_result = await db.execute(
                select(CoverLetter).where(CoverLetter.id == application.cover_letter_id)
            )
            cl = cl_result.scalar_one_or_none()
            if cl:
                # Prefer submitted text over generated text
                letter_text = getattr(cl, "submitted_text", None) or cl.content

        # Load the associated job for context
        job_result = await db.execute(select(Job).where(Job.id == application.job_id))
        job = job_result.scalar_one_or_none()
        if job:
            job_title = job.title
            job_skills = job.skills_required or []
            # Last resort: if no cover letter linked, skip — nothing to promote
            if not letter_text:
                return

        if not letter_text:
            return

        # Check if a promoted proposal already exists for this job
        existing_result = await db.execute(
            select(Proposal).where(
                Proposal.user_id == user_id,
                Proposal.job_id == application.job_id,
                Proposal.source == "extension",
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Update existing proposal to mark as hired
            existing.was_hired = True
            existing.cover_letter_text = letter_text
            if existing.embedding is None:
                existing.embedding = await generate_embedding(letter_text)
        else:
            # Create new promoted proposal
            embedding = await generate_embedding(letter_text)
            proposal = Proposal(
                user_id=user_id,
                job_id=application.job_id,
                cover_letter_text=letter_text,
                job_title=job_title,
                job_skills=job_skills,
                was_hired=True,
                source="extension",
                submitted_at=application.submitted_at or application.outcome_recorded_at,
                embedding=embedding,
            )
            db.add(proposal)

        await db.commit()
    except Exception:
        # Promotion failure must never break the outcome update
        pass


@router.post("/backfill-proposals", response_model=dict)
async def backfill_proposals_corpus(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Backfill proposals corpus from historical applications.

    Scans all non-draft applications that have a cover letter and creates a
    proposals corpus entry for each one that doesn't already have one.
    Sets was_hired=True for HIRED/OFFERED, was_hired=False for DECLINED/WITHDRAWN,
    was_hired=None for in-progress statuses.

    Safe to call multiple times — never downgrades an existing was_hired=True entry.
    """
    import traceback as _tb
    try:
      result = await db.execute(
          select(Application, CoverLetter, Job)
          .join(CoverLetter, Application.cover_letter_id == CoverLetter.id)
          .join(Job, Application.job_id == Job.id)
          .where(Application.user_id == current_user.id)
          .where(cast(Application.status, String) != ApplicationStatus.DRAFT.value)
          .where(Application.cover_letter_id.isnot(None))
      )
      rows = result.all()
    except Exception as _e:
      raise HTTPException(status_code=500, detail=f"{_e}\n{_tb.format_exc()}")

    created = 0
    updated = 0
    skipped = 0

    for app, letter, job in rows:
        if app.status in [ApplicationStatus.HIRED, ApplicationStatus.OFFERED]:
            was_hired = True
        elif app.status in [ApplicationStatus.DECLINED, ApplicationStatus.WITHDRAWN]:
            was_hired = False
        else:
            was_hired = None  # SUBMITTED, VIEWED, RESPONDED, INTERVIEWED

        text = letter.submitted_text if letter.submitted_text else letter.content
        if not text:
            skipped += 1
            continue

        # Check for existing proposal by job_id + source
        existing_result = await db.execute(
            select(Proposal).where(
                Proposal.user_id == current_user.id,
                Proposal.job_id == job.id,
                Proposal.source == "extension",
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Only upgrade was_hired, never downgrade
            if existing.was_hired is not True and was_hired is True:
                existing.was_hired = True
                updated += 1
            else:
                skipped += 1
            continue

        snippet = (job.description or "")[:500]
        proposal = Proposal(
            user_id=current_user.id,
            job_id=job.id,
            cover_letter_text=text,
            job_title=job.title,
            job_description_snippet=snippet,
            job_skills=job.skills_required,
            upwork_job_url=job.upwork_url,
            was_hired=was_hired,
            status=app.status.value,
            source="extension",
            submitted_at=app.submitted_at or app.created_at,
        )
        db.add(proposal)

        try:
            embedding_text = f"Job: {job.title}\n\n{snippet}\n\nProposal:\n{text}"
            proposal.embedding = await generate_embedding(embedding_text)
        except Exception:
            pass  # proceed without embedding

        created += 1

    await db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "total": len(rows)}


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
