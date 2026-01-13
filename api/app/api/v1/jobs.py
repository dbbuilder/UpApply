"""Job and cover letter endpoints."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.embeddings import generate_embedding
from app.core.config import settings
from app.models.user import User, UserProfile
from app.models.job import Job
from app.models.cover_letter import CoverLetter
from app.schemas.job import (
    JobCreate,
    JobResponse,
    JobAnalysisRequest,
    JobAnalysisResponse,
    CoverLetterGenerateRequest,
    CoverLetterResponse,
    CoverLetterRegenerateRequest,
    ExtractAttachmentsRequest,
    ExtractAttachmentsResponse,
    AttachmentMetadata,
)
from app.services.job_analysis import (
    analyze_skill_match,
    find_relevant_memories,
    find_relevant_proposals,
    check_deal_breakers,
    generate_strengths_and_concerns,
    calculate_match_score,
    generate_recommendation,
)
from app.services.cover_letter import (
    generate_cover_letter,
    regenerate_cover_letter,
)

router = APIRouter()


async def get_user_profile(
    current_user: User,
    db: AsyncSession,
) -> UserProfile:
    """Get user profile or raise error."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile not set up. Please complete profile setup first.",
        )

    return profile


@router.post("/analyze", response_model=JobAnalysisResponse)
async def analyze_job(
    request: JobAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze a job against user profile without saving."""
    profile = await get_user_profile(current_user, db)

    job_skills = request.skills_required or []
    client_info = request.client_info.model_dump() if request.client_info else None

    # Analyze skill match
    skill_matches, missing_skills = await analyze_skill_match(job_skills, profile)

    # Find relevant memories
    relevant_memories = await find_relevant_memories(
        db=db,
        user_id=current_user.id,
        job_description=request.description,
        job_skills=job_skills,
        limit=5,
    )

    # Check deal breakers
    deal_breakers = check_deal_breakers(
        job_description=request.description,
        job_skills=job_skills,
        budget_amount=request.budget_amount,
        budget_min=None,  # Not in analysis request
        client_info=client_info,
        profile=profile,
    )

    # Generate strengths and concerns
    strengths, concerns = generate_strengths_and_concerns(
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        relevant_memories=relevant_memories,
        profile=profile,
        budget_amount=request.budget_amount,
    )

    # Calculate match score
    match_score = calculate_match_score(
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        relevant_memories=relevant_memories,
        deal_breakers=deal_breakers,
        profile=profile,
    )

    # Generate recommendation
    recommendation = generate_recommendation(match_score, deal_breakers, concerns)

    return JobAnalysisResponse(
        match_score=match_score,
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        strengths=strengths,
        concerns=concerns,
        deal_breaker_warnings=deal_breakers,
        relevant_memories=relevant_memories,
        recommendation=recommendation,
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    job_data: JobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a job and analyze it."""
    profile = await get_user_profile(current_user, db)

    # Check if job already exists for this user
    result = await db.execute(
        select(Job).where(
            Job.user_id == current_user.id,
            Job.upwork_url == job_data.upwork_url,
        )
    )
    existing_job = result.scalar_one_or_none()

    if existing_job:
        return existing_job

    job_skills = job_data.skills_required or []
    client_info = job_data.client_info.model_dump() if job_data.client_info else None

    # Generate embedding for the job
    job_text = f"{job_data.title}\n{job_data.description}"
    if job_skills:
        job_text += f"\nSkills: {', '.join(job_skills)}"
    embedding = await generate_embedding(job_text)

    # Analyze the job
    skill_matches, missing_skills = await analyze_skill_match(job_skills, profile)

    relevant_memories = await find_relevant_memories(
        db=db,
        user_id=current_user.id,
        job_description=job_data.description,
        job_skills=job_skills,
        limit=5,
    )

    deal_breakers = check_deal_breakers(
        job_description=job_data.description,
        job_skills=job_skills,
        budget_amount=job_data.budget_amount,
        budget_min=job_data.budget_min,
        client_info=client_info,
        profile=profile,
    )

    strengths, concerns = generate_strengths_and_concerns(
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        relevant_memories=relevant_memories,
        profile=profile,
        budget_amount=job_data.budget_amount,
    )

    match_score = calculate_match_score(
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        relevant_memories=relevant_memories,
        deal_breakers=deal_breakers,
        profile=profile,
    )

    recommendation = generate_recommendation(match_score, deal_breakers, concerns)

    # Build analysis dict
    analysis = {
        "skill_matches": [m.model_dump() for m in skill_matches],
        "missing_skills": missing_skills,
        "strengths": strengths,
        "concerns": concerns,
        "deal_breaker_warnings": deal_breakers,
        "relevant_memory_ids": [m["id"] for m in relevant_memories],
        "recommendation": recommendation,
    }

    # Create job
    job = Job(
        user_id=current_user.id,
        upwork_url=job_data.upwork_url,
        upwork_job_id=job_data.upwork_job_id,
        title=job_data.title,
        description=job_data.description,
        budget_type=job_data.budget_type,
        budget_amount=job_data.budget_amount,
        budget_min=job_data.budget_min,
        budget_max=job_data.budget_max,
        skills_required=job_skills,
        experience_level=job_data.experience_level,
        project_length=job_data.project_length,
        client_info=client_info,
        posted_date=job_data.posted_date,
        scraped_at=datetime.utcnow(),
        embedding=embedding,
        match_score=match_score,
        analysis=analysis,
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    return job


@router.get("", response_model=List[JobResponse])
async def list_jobs(
    limit: int = 50,
    offset: int = 0,
    min_score: Optional[float] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's saved jobs."""
    query = select(Job).where(Job.user_id == current_user.id)

    if min_score is not None:
        query = query.where(Job.match_score >= min_score)

    query = query.order_by(Job.match_score.desc(), Job.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return jobs


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return job


@router.get("/{job_id}/match", response_model=JobAnalysisResponse)
async def get_job_match(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed match breakdown for a job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Get fresh analysis
    profile = await get_user_profile(current_user, db)
    job_skills = job.skills_required or []
    client_info = job.client_info

    skill_matches, missing_skills = await analyze_skill_match(job_skills, profile)

    relevant_memories = await find_relevant_memories(
        db=db,
        user_id=current_user.id,
        job_description=job.description,
        job_skills=job_skills,
        limit=5,
    )

    deal_breakers = check_deal_breakers(
        job_description=job.description,
        job_skills=job_skills,
        budget_amount=job.budget_amount,
        budget_min=job.budget_min,
        client_info=client_info,
        profile=profile,
    )

    strengths, concerns = generate_strengths_and_concerns(
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        relevant_memories=relevant_memories,
        profile=profile,
        budget_amount=job.budget_amount,
    )

    match_score = calculate_match_score(
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        relevant_memories=relevant_memories,
        deal_breakers=deal_breakers,
        profile=profile,
    )

    recommendation = generate_recommendation(match_score, deal_breakers, concerns)

    return JobAnalysisResponse(
        match_score=match_score,
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        strengths=strengths,
        concerns=concerns,
        deal_breaker_warnings=deal_breakers,
        relevant_memories=relevant_memories,
        recommendation=recommendation,
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    await db.delete(job)
    await db.commit()


# Cover Letter endpoints

@router.post("/cover-letters/generate", response_model=CoverLetterResponse)
async def generate_cover_letter_endpoint(
    request: CoverLetterGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a cover letter for a job."""
    profile = await get_user_profile(current_user, db)

    # Get job data
    if request.job_id:
        result = await db.execute(
            select(Job).where(Job.id == request.job_id, Job.user_id == current_user.id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )
        job_title = job.title
        job_description = job.description
        job_skills = job.skills_required or []
        budget = job.budget_amount
        job_id = job.id
    elif request.job_data:
        # Create job first
        job_data = request.job_data
        job_skills = job_data.skills_required or []
        client_info = job_data.client_info.model_dump() if job_data.client_info else None

        # Generate embedding
        job_text = f"{job_data.title}\n{job_data.description}"
        if job_skills:
            job_text += f"\nSkills: {', '.join(job_skills)}"
        embedding = await generate_embedding(job_text)

        # Analyze
        skill_matches, missing_skills = await analyze_skill_match(job_skills, profile)
        relevant_memories = await find_relevant_memories(
            db=db,
            user_id=current_user.id,
            job_description=job_data.description,
            job_skills=job_skills,
            limit=5,
        )
        deal_breakers = check_deal_breakers(
            job_description=job_data.description,
            job_skills=job_skills,
            budget_amount=job_data.budget_amount,
            budget_min=job_data.budget_min,
            client_info=client_info,
            profile=profile,
        )
        strengths, concerns = generate_strengths_and_concerns(
            skill_matches=skill_matches,
            missing_skills=missing_skills,
            relevant_memories=relevant_memories,
            profile=profile,
            budget_amount=job_data.budget_amount,
        )
        match_score = calculate_match_score(
            skill_matches=skill_matches,
            missing_skills=missing_skills,
            relevant_memories=relevant_memories,
            deal_breakers=deal_breakers,
            profile=profile,
        )

        analysis = {
            "skill_matches": [m.model_dump() for m in skill_matches],
            "missing_skills": missing_skills,
            "strengths": strengths,
            "concerns": concerns,
            "deal_breaker_warnings": deal_breakers,
            "relevant_memory_ids": [m["id"] for m in relevant_memories],
            "recommendation": generate_recommendation(match_score, deal_breakers, concerns),
        }

        job = Job(
            user_id=current_user.id,
            upwork_url=job_data.upwork_url,
            upwork_job_id=job_data.upwork_job_id,
            title=job_data.title,
            description=job_data.description,
            budget_type=job_data.budget_type,
            budget_amount=job_data.budget_amount,
            budget_min=job_data.budget_min,
            budget_max=job_data.budget_max,
            skills_required=job_skills,
            experience_level=job_data.experience_level,
            project_length=job_data.project_length,
            client_info=client_info,
            posted_date=job_data.posted_date,
            scraped_at=datetime.utcnow(),
            embedding=embedding,
            match_score=match_score,
            analysis=analysis,
        )
        db.add(job)
        await db.flush()

        job_title = job_data.title
        job_description = job_data.description
        budget = job_data.budget_amount
        job_id = job.id
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either job_id or job_data must be provided",
        )

    # Get skill matches, memories, and past proposals
    skill_matches, missing_skills = await analyze_skill_match(job_skills, profile)
    relevant_memories = await find_relevant_memories(
        db=db,
        user_id=current_user.id,
        job_description=job_description,
        job_skills=job_skills,
        limit=5,
    )

    # Find relevant past proposals to use as writing examples
    past_proposals = await find_relevant_proposals(
        db=db,
        user_id=current_user.id,
        job_description=job_description,
        job_skills=job_skills,
        limit=3,  # Top 3 most similar past proposals
        successful_only=False,  # Include all, but successful ones are prioritized
    )

    # Generate cover letter
    content = await generate_cover_letter(
        job_title=job_title,
        job_description=job_description,
        job_skills=job_skills,
        budget=budget,
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        relevant_memories=relevant_memories,
        profile=profile,
        past_proposals=past_proposals,
    )

    # Save cover letter
    cover_letter = CoverLetter(
        user_id=current_user.id,
        job_id=job_id,
        content=content,
        model_used=settings.default_model,
        memories_used=[m["id"] for m in relevant_memories],
        version=1,
    )
    db.add(cover_letter)
    await db.commit()
    await db.refresh(cover_letter)

    # Get match score
    match_score = None
    if request.job_id:
        result = await db.execute(
            select(Job).where(Job.id == job_id)
        )
        job_record = result.scalar_one_or_none()
        if job_record:
            match_score = job_record.match_score

    return CoverLetterResponse(
        id=cover_letter.id,
        user_id=cover_letter.user_id,
        job_id=cover_letter.job_id,
        content=cover_letter.content,
        model_used=cover_letter.model_used,
        memories_used=cover_letter.memories_used,
        word_count=len(content.split()),
        version=cover_letter.version,
        is_final=False,
        created_at=cover_letter.created_at,
        match_score=match_score,
        highlighted_skills=[m.skill for m in skill_matches if m.match_type == "exact"],
    )


@router.get("/cover-letters", response_model=List[CoverLetterResponse])
async def list_cover_letters(
    job_id: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's cover letters."""
    query = select(CoverLetter).where(CoverLetter.user_id == current_user.id)

    if job_id:
        query = query.where(CoverLetter.job_id == job_id)

    query = query.order_by(CoverLetter.created_at.desc()).limit(limit)

    result = await db.execute(query)
    letters = result.scalars().all()

    return [
        CoverLetterResponse(
            id=cl.id,
            user_id=cl.user_id,
            job_id=cl.job_id,
            content=cl.content,
            model_used=cl.model_used,
            memories_used=cl.memories_used,
            word_count=len(cl.content.split()),
            version=cl.version,
            is_final=False,
            created_at=cl.created_at,
        )
        for cl in letters
    ]


@router.post("/cover-letters/{letter_id}/regenerate", response_model=CoverLetterResponse)
async def regenerate_cover_letter_endpoint(
    letter_id: str,
    request: CoverLetterRegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate a cover letter with feedback."""
    profile = await get_user_profile(current_user, db)

    # Get existing cover letter
    result = await db.execute(
        select(CoverLetter).where(
            CoverLetter.id == letter_id,
            CoverLetter.user_id == current_user.id,
        )
    )
    existing = result.scalar_one_or_none()

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover letter not found",
        )

    # Get job
    result = await db.execute(
        select(Job).where(Job.id == existing.job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated job not found",
        )

    # Regenerate
    if request.feedback:
        content = await regenerate_cover_letter(
            original_letter=existing.content,
            feedback=request.feedback,
            job_title=job.title,
            job_description=job.description,
            profile=profile,
        )
    else:
        # Generate fresh
        job_skills = job.skills_required or []
        skill_matches, missing_skills = await analyze_skill_match(job_skills, profile)
        relevant_memories = await find_relevant_memories(
            db=db,
            user_id=current_user.id,
            job_description=job.description,
            job_skills=job_skills,
            limit=5,
        )

        # Find relevant past proposals
        past_proposals = await find_relevant_proposals(
            db=db,
            user_id=current_user.id,
            job_description=job.description,
            job_skills=job_skills,
            limit=3,
        )

        content = await generate_cover_letter(
            job_title=job.title,
            job_description=job.description,
            job_skills=job_skills,
            budget=job.budget_amount,
            skill_matches=skill_matches,
            missing_skills=missing_skills,
            relevant_memories=relevant_memories,
            profile=profile,
            past_proposals=past_proposals,
        )

    # Create new version
    new_letter = CoverLetter(
        user_id=current_user.id,
        job_id=job.id,
        content=content,
        model_used=settings.default_model,
        memories_used=existing.memories_used,
        version=existing.version + 1,
    )
    db.add(new_letter)
    await db.commit()
    await db.refresh(new_letter)

    return CoverLetterResponse(
        id=new_letter.id,
        user_id=new_letter.user_id,
        job_id=new_letter.job_id,
        content=new_letter.content,
        model_used=new_letter.model_used,
        memories_used=new_letter.memories_used,
        word_count=len(content.split()),
        version=new_letter.version,
        is_final=False,
        created_at=new_letter.created_at,
        match_score=job.match_score,
    )


# Attachment extraction endpoints

@router.post("/{job_id}/extract-attachments", response_model=ExtractAttachmentsResponse)
async def extract_job_attachments(
    job_id: str,
    request: ExtractAttachmentsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract text from job attachments and update job record."""
    from app.services.text_extraction import extract_all_attachments

    # Get the job
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Extract text from all attachments
    attachments_data = [
        {
            "data": att.data,
            "filename": att.filename,
            "content_type": att.content_type,
        }
        for att in request.attachments
    ]

    combined_text, metadata = await extract_all_attachments(attachments_data)

    # Collect errors
    extraction_errors = [
        f"{m['filename']}: {m['error']}"
        for m in metadata
        if m.get("error")
    ]

    # Update job with extracted content
    if request.full_description:
        job.full_description = request.full_description
    if combined_text:
        job.attachment_text = combined_text
    job.attachment_metadata = metadata

    # Regenerate embedding if we have new content
    if combined_text or request.full_description:
        # Combine all text for embedding
        all_text = job.title
        if request.full_description:
            all_text += f"\n{request.full_description}"
        elif job.description:
            all_text += f"\n{job.description}"
        if combined_text:
            all_text += f"\n{combined_text}"
        if job.skills_required:
            all_text += f"\nSkills: {', '.join(job.skills_required)}"

        # Generate new embedding
        new_embedding = await generate_embedding(all_text[:8000])  # Limit to ~8k chars
        job.embedding = new_embedding

    await db.commit()
    await db.refresh(job)

    return ExtractAttachmentsResponse(
        job_id=job.id,
        attachment_text=combined_text,
        full_description=request.full_description,
        attachment_count=len(request.attachments),
        attachment_metadata=[
            AttachmentMetadata(**m) for m in metadata
        ],
        extraction_errors=extraction_errors,
    )
