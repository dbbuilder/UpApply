"""Job and cover letter endpoints."""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.core.rate_limit import limiter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.embeddings import generate_embedding
from app.core.config import settings
from app.core.errors import generation_unavailable
from app.models.user import User, UserProfile
from app.models.job import Job
from app.models.cover_letter import CoverLetter
from app.models.application import Application, ApplicationStatus
from app.models.proposal import Proposal
from app.api.v1.proposals import _job_needs_embedding
from app.schemas.job import (
    JobCreate,
    JobResponse,
    JobAnalysisRequest,
    JobAnalysisResponse,
    CoverLetterGenerateRequest,
    CoverLetterResponse,
    CoverLetterRegenerateRequest,
    CoverLetterSubmitRequest,
    CoverLetterImproveResponse,
    CoverLetterRefineRequest,
    CoverLetterRefineResponse,
    CoverLetterFinalRequest,
    CoverLetterFinalResponse,
    ExtractAttachmentsRequest,
    ExtractAttachmentsResponse,
    AttachmentMetadata,
    JobBulkImportRequest,
    ContractImportRequest,
    ContractImportResponse,
    SuggestMilestonesRequest,
    SuggestMilestonesResponse,
    MilestoneSuggestion,
    MAX_FINAL_ANSWER,
)
from app.models.proposal import Proposal
from app.services.job_analysis import (
    find_relevant_proposals,
    run_full_analysis,
)
from app.services.cover_letter import (
    generate_cover_letter,
    regenerate_cover_letter,
    improve_cover_letter,
)
from app.services.generation import generate_application
from app.services.generation.evidence import EvidenceUnavailable
from app.services.llm import LLMError
from app.models.fact import Fact
from app.services.facts import credit_facts, upsert_candidate
from app.services.outcomes import apply_outcome
from app.services.fact_extraction import extract_facts
from app.services.generation.brief import JobBrief
from app.services.generation.evidence import Evidence
from app.services.generation.writer import Draft
from app.services.generation.refine import MAX_HISTORY, RefineError, refine_application
from app.services.edit_distance import word_edit_distance_pct

logger = logging.getLogger(__name__)
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

    result = await run_full_analysis(
        db=db,
        user_id=current_user.id,
        profile=profile,
        job_title=request.title,
        job_description=request.description,
        job_skills=job_skills,
        budget_amount=request.budget_amount,
        client_info=client_info,
    )

    return JobAnalysisResponse(
        match_score=result.match_score,
        skill_matches=result.skill_matches,
        missing_skills=result.missing_skills,
        strengths=result.strengths,
        concerns=result.concerns,
        deal_breaker_warnings=result.deal_breaker_warnings,
        relevant_memories=result.relevant_memories,
        recommendation=result.recommendation,
        reason=result.reason,
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
        # If the incoming description is substantially longer than the stored one
        # (i.e. the stored one was a stub like just the title), re-analyze and update.
        existing_desc = existing_job.description or ""
        incoming_desc = job_data.description or ""
        if len(incoming_desc) > len(existing_desc) + 50:
            try:
                job_skills = job_data.skills_required or []
                client_info = job_data.client_info.model_dump() if job_data.client_info else None
                reanalysis = await run_full_analysis(
                    db=db,
                    user_id=current_user.id,
                    profile=profile,
                    job_description=incoming_desc,
                    job_skills=job_skills,
                    budget_amount=job_data.budget_amount,
                    budget_min=job_data.budget_min,
                    client_info=client_info,
                )
                existing_job.description = incoming_desc
                if job_data.full_description:
                    existing_job.full_description = job_data.full_description
                existing_job.match_score = reanalysis.match_score
                existing_job.analysis = {
                    "skill_matches": [m.model_dump() for m in reanalysis.skill_matches],
                    "missing_skills": reanalysis.missing_skills,
                    "strengths": reanalysis.strengths,
                    "concerns": reanalysis.concerns,
                    "deal_breaker_warnings": reanalysis.deal_breaker_warnings,
                    "relevant_memory_ids": [m["id"] for m in reanalysis.relevant_memories],
                    "recommendation": reanalysis.recommendation,
                }
                await db.commit()
                await db.refresh(existing_job)
            except Exception:
                pass  # non-critical — return existing job as-is
        return existing_job

    job_skills = job_data.skills_required or []
    client_info = job_data.client_info.model_dump() if job_data.client_info else None

    # Generate embedding for the job (best-effort)
    job_text = f"{job_data.title}\n{job_data.description}"
    if job_skills:
        job_text += f"\nSkills: {', '.join(job_skills)}"
    try:
        from tenacity import RetryError
        embedding = await generate_embedding(job_text)
    except (RetryError, Exception):
        embedding = None

    # Run full analysis — pass the embedding we just computed so run_full_analysis
    # doesn't make a second identical OpenAI call for the same text.
    result = await run_full_analysis(
        db=db,
        user_id=current_user.id,
        profile=profile,
        job_description=job_data.description,
        job_skills=job_skills,
        budget_amount=job_data.budget_amount,
        budget_min=job_data.budget_min,
        client_info=client_info,
        precomputed_embedding=embedding,
    )

    # Build analysis dict
    analysis = {
        "skill_matches": [m.model_dump() for m in result.skill_matches],
        "missing_skills": result.missing_skills,
        "strengths": result.strengths,
        "concerns": result.concerns,
        "deal_breaker_warnings": result.deal_breaker_warnings,
        "relevant_memory_ids": [m["id"] for m in result.relevant_memories],
        "recommendation": result.recommendation,
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
        scraped_at=datetime.now(timezone.utc),
        embedding=embedding,
        match_score=result.match_score,
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
    source: Optional[str] = None,
    is_saved: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's saved jobs."""
    query = select(Job).where(Job.user_id == current_user.id)

    if min_score is not None:
        query = query.where(Job.match_score >= min_score)
    if source is not None:
        query = query.where(Job.source == source)
    if is_saved is not None:
        query = query.where(Job.is_saved == is_saved)

    # Exclude expired search results
    query = query.where(
        (Job.expires_at == None) | (Job.expires_at > datetime.now(timezone.utc))  # noqa: E711
    )

    query = query.order_by(Job.match_score.desc(), Job.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return jobs


@router.get("/active-contracts", response_model=List[JobResponse])
async def get_active_contracts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return imported contracts that are still active or paused on Upwork.

    Contract status is stored in Application.outcome_notes as
    'Imported from contract history. Status: active|paused|ended'.
    """
    from sqlalchemy import text as sa_text
    sql = sa_text("""
        SELECT DISTINCT j.*
        FROM jobs j
        JOIN applications a ON a.job_id = j.id AND a.user_id = j.user_id
        WHERE j.user_id = :user_id
          AND j.source = 'contract_import'
          AND (
              a.outcome_notes ILIKE '%Status: active%'
           OR a.outcome_notes ILIKE '%Status: paused%'
          )
        ORDER BY j.created_at DESC
        LIMIT 50
    """)
    result = await db.execute(sql, {"user_id": current_user.id})
    rows = result.fetchall()

    # Map raw rows to Job ORM objects
    job_ids = [row[0] for row in rows]
    if not job_ids:
        return []
    job_q = select(Job).where(Job.id.in_(job_ids)).order_by(Job.created_at.desc())
    jobs_result = await db.execute(job_q)
    return jobs_result.scalars().all()


@router.post("/import-bulk", response_model=List[JobResponse])
async def import_bulk_jobs(
    request: JobBulkImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import jobs from saved list or search results, running analysis on each."""
    profile = await get_user_profile(current_user, db)
    created_jobs: list[Job] = []
    expires_at = None
    if request.source == "search":
        expires_at = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + __import__("datetime").timedelta(days=7)

    for item in request.jobs:
        # Skip duplicates
        existing = await db.execute(
            select(Job).where(
                Job.user_id == current_user.id,
                Job.upwork_job_id == item.upwork_job_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Generate embedding (best-effort)
        job_text = f"{item.title}\n{item.description}"
        if item.skills:
            job_text += f"\nSkills: {', '.join(item.skills)}"
        try:
            from tenacity import RetryError
            embedding = await generate_embedding(job_text)
        except (RetryError, Exception):
            embedding = None

        # Run analysis
        ar = await run_full_analysis(
            db=db,
            user_id=current_user.id,
            profile=profile,
            job_description=item.description,
            job_skills=item.skills or [],
            client_info=item.client_info,
        )

        analysis = {
            "skill_matches": [m.model_dump() for m in ar.skill_matches],
            "missing_skills": ar.missing_skills,
            "strengths": ar.strengths,
            "concerns": ar.concerns,
            "deal_breaker_warnings": ar.deal_breaker_warnings,
            "recommendation": ar.recommendation,
        }

        job = Job(
            user_id=current_user.id,
            upwork_job_id=item.upwork_job_id,
            upwork_url=item.upwork_url,
            title=item.title,
            description=item.description,
            budget_type=item.job_type,
            skills_required=item.skills or [],
            experience_level=item.experience_level,
            client_info=item.client_info,
            embedding=embedding,
            match_score=ar.match_score,
            analysis=analysis,
            is_saved=request.source == "saved",
            source=request.source,
            expires_at=expires_at,
            scraped_at=datetime.now(timezone.utc),
        )
        db.add(job)
        created_jobs.append(job)

    await db.commit()
    for job in created_jobs:
        await db.refresh(job)

    return created_jobs


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

    result = await run_full_analysis(
        db=db,
        user_id=current_user.id,
        profile=profile,
        job_description=job.description,
        job_skills=job_skills,
        budget_amount=job.budget_amount,
        budget_min=job.budget_min,
        client_info=job.client_info,
    )

    return JobAnalysisResponse(
        match_score=result.match_score,
        skill_matches=result.skill_matches,
        missing_skills=result.missing_skills,
        strengths=result.strengths,
        concerns=result.concerns,
        deal_breaker_warnings=result.deal_breaker_warnings,
        relevant_memories=result.relevant_memories,
        recommendation=result.recommendation,
        reason=result.reason,
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


@router.post("/import-contracts", response_model=ContractImportResponse)
async def import_contracts(
    request: ContractImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import Upwork contract history as won jobs for scoring calibration."""
    import asyncio
    imported = 0
    updated = 0

    # Pre-fetch all existing jobs to avoid N+1 queries
    upwork_ids = [f"contract_{c.contract_id}" for c in request.contracts]
    existing_result = await db.execute(
        select(Job).where(
            Job.user_id == current_user.id,
            Job.upwork_job_id.in_(upwork_ids),
        )
    )
    existing_map = {j.upwork_job_id: j for j in existing_result.scalars().all()}

    # Build descriptions for all contracts
    descriptions = []
    for contract in request.contracts:
        parts = [contract.title]
        if contract.rate:
            parts.append(f"Rate: {contract.rate}")
        if contract.client_name:
            parts.append(f"Client: {contract.client_name}")
        if contract.date_range:
            parts.append(f"Dates: {contract.date_range}")
        descriptions.append("\n".join(parts))

    # Generate all embeddings in parallel, skipping contracts that already have them
    needs_embedding = [
        i for i, c in enumerate(request.contracts)
        if f"contract_{c.contract_id}" not in existing_map
        or existing_map[f"contract_{c.contract_id}"].embedding is None
    ]
    try:
        from tenacity import RetryError
        embed_tasks = [generate_embedding(descriptions[i]) for i in needs_embedding]
        embeddings_list = await asyncio.gather(*embed_tasks) if embed_tasks else []
    except (RetryError, Exception):
        embeddings_list = [None] * len(needs_embedding)
    embedding_by_idx = dict(zip(needs_embedding, embeddings_list))

    for idx, contract in enumerate(request.contracts):
        upwork_job_id = f"contract_{contract.contract_id}"
        existing_job = existing_map.get(upwork_job_id)
        description = descriptions[idx]
        embedding = embedding_by_idx.get(idx)

        if existing_job:
            # Update embedding if missing; always count as synced
            if existing_job.embedding is None and embedding is not None:
                existing_job.embedding = embedding
            updated += 1
            job = existing_job
        else:
            job = Job(
                user_id=current_user.id,
                upwork_job_id=upwork_job_id,
                upwork_url=f"https://www.upwork.com/nx/wm/workroom/{contract.contract_id}/overview",
                title=contract.title,
                description=description,
                budget_type=contract.contract_type if contract.contract_type != "unknown" else None,
                budget_amount=contract.rate,
                client_info={"name": contract.client_name} if contract.client_name else None,
                is_saved=True,
                source="contract_import",
                match_score=100.0,  # Won contracts are calibration anchors
                embedding=embedding,
            )
            db.add(job)
            await db.flush()  # Materialise job.id before creating Application
            imported += 1

        # Ensure an Application record exists with HIRED status
        existing_app = await db.execute(
            select(Application).where(
                Application.user_id == current_user.id,
                Application.job_id == job.id,
            )
        )
        app = existing_app.scalar_one_or_none()
        if not app:
            app = Application(
                user_id=current_user.id,
                job_id=job.id,
                status=ApplicationStatus.HIRED,
                outcome_notes=f"Imported from contract history. Status: {contract.status}",
            )
            db.add(app)
        elif app.status != ApplicationStatus.HIRED:
            app.status = ApplicationStatus.HIRED

        # If a winning proposal text was scraped, create/update a Proposal record
        if contract.cover_letter_text and contract.cover_letter_text.strip():
            workroom_url = f"https://www.upwork.com/nx/wm/workroom/{contract.contract_id}/overview"
            existing_prop = await db.execute(
                select(Proposal).where(
                    Proposal.user_id == current_user.id,
                    Proposal.upwork_job_url == workroom_url,
                )
            )
            prop = existing_prop.scalar_one_or_none()
            if prop:
                prop.cover_letter_text = contract.cover_letter_text.strip()
                prop.job_id = job.id
                await apply_outcome(db, prop, "hired")  # sets was_hired; credits facts once
                prop.was_hired = True
                if prop.job_needs_embedding is None:
                    prop.job_needs_embedding = await _job_needs_embedding(job.title, job.description)
            else:
                try:
                    from tenacity import RetryError
                    prop_embedding = await generate_embedding(contract.cover_letter_text.strip())
                except (RetryError, Exception):
                    prop_embedding = None
                prop = Proposal(
                    user_id=current_user.id,
                    job_id=job.id,
                    upwork_job_url=workroom_url,
                    job_title=contract.title,
                    cover_letter_text=contract.cover_letter_text.strip(),
                    was_hired=True,
                    status="hired",
                    source="contract_import",
                    embedding=prop_embedding,
                    job_needs_embedding=await _job_needs_embedding(job.title, job.description),
                )
                db.add(prop)
                await db.flush()
                await apply_outcome(db, prop, "hired")  # credits the job's letter facts once

    await db.commit()
    return ContractImportResponse(imported=imported, updated=updated, total=len(request.contracts))


# Milestone suggestion endpoint

@router.post("/suggest-milestones", response_model=SuggestMilestonesResponse)
async def suggest_milestones(
    request: SuggestMilestonesRequest,
    current_user: User = Depends(get_current_user),
):
    """Suggest milestones for a fixed-price Upwork contract."""
    import json
    import re
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Parse total budget from string like "$500" or "$1,500"
    total_budget: Optional[float] = None
    if request.budget_amount:
        amount_match = re.search(r"[\d,]+\.?\d*", request.budget_amount.replace(",", ""))
        if amount_match:
            try:
                total_budget = float(amount_match.group().replace(",", ""))
            except ValueError:
                pass

    budget_context = ""
    if total_budget:
        budget_context = f"The total budget is {request.budget_amount} (${total_budget:.2f}). The milestone amounts MUST sum to approximately ${total_budget:.2f}."
    else:
        budget_context = "No specific budget was provided. Use reasonable amounts based on the project scope."

    user_prompt = f"""Job Title: {request.job_title}

Job Description:
{request.job_description[:2000]}

{budget_context}

Suggest exactly {request.num_milestones} milestones for this fixed-price contract.
Return a JSON object with a "milestones" array. Each milestone has:
- "description": string (concise deliverable description, max 80 chars)
- "days_from_start": integer (when this milestone is due, e.g. 14, 30, 45)
- "amount": number (dollar amount for this milestone)"""

    response = await client.chat.completions.create(
        model=settings.default_model,
        messages=[
            {
                "role": "system",
                "content": "You are a project scoping assistant. Given a job description and budget, suggest milestones for a fixed-price Upwork contract. Return JSON.",
            },
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=400,
        temperature=0,
    )

    data = json.loads(response.choices[0].message.content)
    raw_milestones = data.get("milestones", [])

    milestones = [
        MilestoneSuggestion(
            description=str(m.get("description", ""))[:80],
            days_from_start=int(m.get("days_from_start", 14)),
            amount=float(m.get("amount", 0)),
        )
        for m in raw_milestones
    ]

    return SuggestMilestonesResponse(milestones=milestones)


# Cover Letter endpoints

@router.post("/cover-letters/generate", response_model=CoverLetterResponse)
@limiter.limit("5/hour")
async def generate_cover_letter_endpoint(
    request: Request,
    body: CoverLetterGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a cover letter for a job."""
    profile = await get_user_profile(current_user, db)

    # Get job data
    if body.job_id:
        result = await db.execute(
            select(Job).where(Job.id == body.job_id, Job.user_id == current_user.id)
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
        ar = await run_full_analysis(
            db=db,
            user_id=current_user.id,
            profile=profile,
            job_description=job_description,
            job_skills=job_skills,
            budget_amount=job.budget_amount,
            client_info=job.client_info,
        )
    elif body.job_data:
        # Create job first
        job_data = body.job_data
        job_skills = job_data.skills_required or []
        client_info = job_data.client_info.model_dump() if job_data.client_info else None

        # Generate embedding (best-effort — None if OpenAI quota exhausted)
        job_text = f"{job_data.title}\n{job_data.description}"
        if job_skills:
            job_text += f"\nSkills: {', '.join(job_skills)}"
        try:
            from tenacity import RetryError
            embedding = await generate_embedding(job_text)
        except (RetryError, Exception):
            embedding = None

        # Run full analysis
        ar = await run_full_analysis(
            db=db,
            user_id=current_user.id,
            profile=profile,
            job_description=job_data.description,
            job_skills=job_skills,
            budget_amount=job_data.budget_amount,
            budget_min=job_data.budget_min,
            client_info=client_info,
        )

        analysis = {
            "skill_matches": [m.model_dump() for m in ar.skill_matches],
            "missing_skills": ar.missing_skills,
            "strengths": ar.strengths,
            "concerns": ar.concerns,
            "deal_breaker_warnings": ar.deal_breaker_warnings,
            "relevant_memory_ids": [m["id"] for m in ar.relevant_memories],
            "recommendation": ar.recommendation,
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
            scraped_at=datetime.now(timezone.utc),
            embedding=embedding,
            match_score=ar.match_score,
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

    skill_matches = ar.skill_matches
    missing_skills = ar.missing_skills
    relevant_memories = ar.relevant_memories

    v2_result = None
    if profile.generation_v2:
        try:
            v2_result = await generate_application(
                db=db,
                user=current_user,
                profile=profile,
                title=job_title,
                description=job_description,
                skills=job_skills,
                questions=body.screening_questions or [],
                include_call_offer=body.include_call_offer,
                prototype_url=body.prototype_url,
                extra_points=body.custom_instructions,
            )
        except EvidenceUnavailable as exc:
            await db.rollback()
            return generation_unavailable(
                exc, status.HTTP_503_SERVICE_UNAVAILABLE,
                "Your experience facts could not be retrieved right now. Please try again shortly.",
            )
        except LLMError as exc:
            await db.rollback()
            return generation_unavailable(
                exc, status.HTTP_502_BAD_GATEWAY,
                "Draft generation is temporarily unavailable. Please try again shortly.",
            )
        content = v2_result.draft.cover_letter
    else:
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
            inclusions=body.custom_instructions,
            prototype_url=body.prototype_url,
            include_call_offer=body.include_call_offer,
        )

    # Save cover letter
    cover_letter = CoverLetter(
        user_id=current_user.id,
        job_id=job_id,
        content=content,
        model_used=settings.cover_letter_model if v2_result else settings.legacy_cover_letter_model,
        memories_used=None if v2_result else [m["id"] for m in relevant_memories],
        version=1,
    )
    v2_fields: dict = {}
    if v2_result:
        cover_letter.prompt_version = "v2"
        cover_letter.word_count = len(content.split())
        cover_letter.brief = v2_result.brief.model_dump()
        cover_letter.fact_ids_used = v2_result.draft.fact_ids_used
        cover_letter.voice_sample_ids = [str(p.id) for p in v2_result.evidence.voice_samples]
        cover_letter.verify_warnings = v2_result.warnings
        cited = set(v2_result.draft.fact_ids_used)
        v2_fields = {
            "screening_answers": v2_result.draft.screening_answers,
            "verify_warnings": v2_result.warnings,
            "claims_verified": v2_result.claims_verified,
            "facts_used": [
                {"id": str(f.id), "statement": f.statement}
                for f in v2_result.evidence.facts
                if str(f.id) in cited
            ],
        }
    db.add(cover_letter)
    await db.commit()
    await db.refresh(cover_letter)

    # Get match score
    match_score = None
    if body.job_id:
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
        **v2_fields,
    )


@router.post("/cover-letters/{letter_id}/regenerate", response_model=CoverLetterResponse)
@limiter.limit("5/hour")
async def regenerate_cover_letter_endpoint(
    request: Request,
    letter_id: str,
    body: CoverLetterRegenerateRequest,
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
    if body.feedback:
        content = await regenerate_cover_letter(
            original_letter=existing.content,
            feedback=body.feedback,
            job_title=job.title,
            job_description=job.description,
            profile=profile,
            include_call_offer=body.include_call_offer,
        )
    else:
        # Generate fresh
        job_skills = job.skills_required or []
        ar = await run_full_analysis(
            db=db,
            user_id=current_user.id,
            profile=profile,
            job_description=job.description,
            job_skills=job_skills,
            budget_amount=job.budget_amount,
            client_info=job.client_info,
        )
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
            skill_matches=ar.skill_matches,
            missing_skills=ar.missing_skills,
            relevant_memories=ar.relevant_memories,
            profile=profile,
            past_proposals=past_proposals,
            include_call_offer=body.include_call_offer,
        )

    # Create new version
    new_letter = CoverLetter(
        user_id=current_user.id,
        job_id=job.id,
        content=content,
        model_used=settings.legacy_cover_letter_model,
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


# ---------------------------------------------------------------------------
# Cover letter feedback loop endpoints
# ---------------------------------------------------------------------------

@router.put("/cover-letters/{letter_id}/submit", response_model=CoverLetterResponse)
async def submit_cover_letter(
    letter_id: str,
    request: CoverLetterSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a cover letter as submitted and capture the final (possibly edited) text.

    Creates a Proposal record so the submitted letter enters the corpus immediately
    as a voice calibration example even before the outcome is known.
    """
    result = await db.execute(
        select(CoverLetter).where(
            CoverLetter.id == letter_id,
            CoverLetter.user_id == current_user.id,
        )
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found")

    letter.submitted_text = request.submitted_text
    letter.was_submitted = True
    letter.submitted_at = datetime.now(timezone.utc)
    await db.flush()

    # Load job for context
    job_result = await db.execute(select(Job).where(Job.id == letter.job_id))
    job = job_result.scalar_one_or_none()

    # Upsert into proposals corpus — source='extension', was_hired=None until outcome known
    if job:
        existing_prop = await db.execute(
            select(Proposal).where(
                Proposal.user_id == current_user.id,
                Proposal.job_id == letter.job_id,
                Proposal.source == "extension",
            )
        )
        prop = existing_prop.scalar_one_or_none()
        if prop:
            prop.cover_letter_text = request.submitted_text
            try:
                from tenacity import RetryError
                prop.embedding = await generate_embedding(request.submitted_text)
            except (RetryError, Exception):
                pass  # Keep existing embedding; corpus entry still saved
            if prop.job_needs_embedding is None:
                prop.job_needs_embedding = await _job_needs_embedding(job.title, job.description)
        else:
            try:
                from tenacity import RetryError
                embedding = await generate_embedding(request.submitted_text)
            except (RetryError, Exception):
                embedding = None
            prop = Proposal(
                user_id=current_user.id,
                job_id=letter.job_id,
                cover_letter_text=request.submitted_text,
                job_title=job.title,
                job_skills=job.skills_required or [],
                was_hired=None,
                source="extension",
                author="chris_edited_ai",  # began as an UpApply draft (matches migration 022)
                job_text=job.description,
                job_needs_embedding=await _job_needs_embedding(job.title, job.description),
                submitted_at=datetime.now(timezone.utc),
                embedding=embedding,
            )
            db.add(prop)

    await db.commit()
    await db.refresh(letter)

    return CoverLetterResponse(
        id=letter.id,
        user_id=letter.user_id,
        job_id=letter.job_id,
        content=letter.content,
        model_used=letter.model_used,
        memories_used=letter.memories_used,
        word_count=len(letter.content.split()),
        version=letter.version,
        is_final=letter.is_final,
        created_at=letter.created_at,
    )


@router.post("/cover-letters/{letter_id}/improve", response_model=CoverLetterImproveResponse)
async def improve_cover_letter_endpoint(
    letter_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare a generated cover letter against past winning letters and produce an improved version.

    Requires at least 2 hired proposals in the corpus for meaningful comparison.
    Stores the improved letter as a new version and returns both the content and
    a list of specific improvement notes.
    """
    # Load the letter to improve
    result = await db.execute(
        select(CoverLetter).where(
            CoverLetter.id == letter_id,
            CoverLetter.user_id == current_user.id,
        )
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found")

    # Load associated job
    job_result = await db.execute(select(Job).where(Job.id == letter.job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated job not found")

    # Load user profile
    profile = await get_user_profile(current_user, db)

    # Find hired proposals semantically similar to this job
    hired_proposals = await find_relevant_proposals(
        db=db,
        user_id=current_user.id,
        job_description=job.description or job.title,
        job_skills=job.skills_required or [],
        limit=3,
        successful_only=True,
    )

    if len(hired_proposals) < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Need at least 1 won proposal in your corpus to improve letters. "
                   "Apply to jobs and mark outcomes as you go.",
        )

    # Call the improvement service
    improved_content, improvement_notes = await improve_cover_letter(
        generated_letter=letter.content,
        job_title=job.title,
        job_description=job.description or "",
        hired_proposals=hired_proposals,
        profile=profile,
    )

    # Store as a new version
    new_letter = CoverLetter(
        user_id=current_user.id,
        job_id=letter.job_id,
        content=improved_content,
        model_used=settings.legacy_cover_letter_model,
        version=letter.version + 1,
        is_final=True,
        memories_used=letter.memories_used,
    )
    db.add(new_letter)
    await db.commit()
    await db.refresh(new_letter)

    return CoverLetterImproveResponse(
        cover_letter_id=new_letter.id,
        improved_content=improved_content,
        improvement_notes=improvement_notes,
        hired_examples_used=len(hired_proposals),
    )


# ---------------------------------------------------------------------------
# Refine + learn loop (spec §3)
# ---------------------------------------------------------------------------

async def _capture_fact_candidates(
    db: AsyncSession,
    user_id: str,
    text: str,
    source_type: str,
    source_ref: Optional[str],
    context: Optional[str] = None,
) -> int:
    """Turn the user's own words into fact candidates. Never fails the request.

    Candidates are never auto-approved here: upsert_candidate applies the spec §1.7 match rule
    (a match to an approved fact stays approved; anything else goes to review)."""
    try:
        candidates = await extract_facts(text, source_type, source_ref=source_ref, context=context)
        async with db.begin_nested():
            for cand in candidates:
                await upsert_candidate(db, user_id, cand)
        return len(candidates)
    except Exception as exc:
        # Content-free: exception messages can carry user or model text.
        logger.warning("Fact capture failed (%s): %s", source_type, type(exc).__name__)
        return 0


@router.post("/cover-letters/{letter_id}/refine", response_model=CoverLetterRefineResponse)
@limiter.limit("30/hour")
async def refine_cover_letter_endpoint(
    request: Request,
    letter_id: str,
    body: CoverLetterRefineRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revise a v2 draft from one refine-thread message (search_facts tool, verify every turn)."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message is empty")

    result = await db.execute(
        select(CoverLetter).where(
            CoverLetter.id == letter_id,
            CoverLetter.user_id == current_user.id,
        )
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found")
    if not letter.brief:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Refine needs a letter generated by the v2 engine. Generate a new draft first.",
        )
    profile = await get_user_profile(current_user, db)

    brief = JobBrief.model_validate(letter.brief)
    known_ids = [str(x) for x in (letter.fact_ids_used or [])]
    facts = []
    if known_ids:
        facts = list((await db.execute(
            select(Fact).where(
                Fact.id.in_(known_ids),
                Fact.user_id == current_user.id,
                Fact.status == "approved",  # a fact rejected since generation is no longer evidence
            )
        )).scalars())
    known_ids = [fid for fid in known_ids if fid in {str(f.id) for f in facts}]
    voice = []
    if letter.voice_sample_ids:
        voice = list((await db.execute(
            select(Proposal).where(
                Proposal.id.in_([str(x) for x in letter.voice_sample_ids]),
                Proposal.user_id == current_user.id,
            )
        )).scalars())

    history = [m for m in (letter.refine_messages or []) if isinstance(m, dict)]
    last = next((m for m in reversed(history) if m.get("role") == "assistant"), None)
    # Revise what the sidebar shows (hand edits included); stored copies are the fallback.
    if body.screening_answers is not None:
        current_answers = [a.model_dump() for a in body.screening_answers]
    else:
        current_answers = list(last.get("screening_answers") or []) if last else []
    current = Draft(
        cover_letter=(body.current_draft or "").strip() or letter.content,
        screening_answers=current_answers,
        fact_ids_used=known_ids,
    )

    try:
        outcome = await refine_application(
            db, current_user.id, profile, brief,
            Evidence(facts=facts, voice_samples=voice), current, history, message,
        )
    except RefineError as exc:
        await db.rollback()
        return generation_unavailable(
            exc, status.HTTP_502_BAD_GATEWAY,
            "Refining is temporarily unavailable. Please try again shortly.",
        )

    draft = outcome.draft
    answers = [
        {"question": str(a.get("question", "")), "answer": str(a.get("answer", ""))[:MAX_FINAL_ANSWER]}
        for a in draft.screening_answers
    ]
    allowed = set(known_ids) | {str(f.id) for f in outcome.found_facts}
    new_ids = [fid for fid in dict.fromkeys(draft.fact_ids_used) if fid in allowed and fid not in known_ids]
    if new_ids:
        letter.fact_ids_used = [*(letter.fact_ids_used or []), *new_ids]
        await credit_facts(db, new_ids, won=False, user_id=current_user.id)  # times_used += 1

    now = datetime.now(timezone.utc).isoformat()
    letter.content = draft.cover_letter
    letter.word_count = len(draft.cover_letter.split())
    letter.model_used = settings.cover_letter_model
    letter.refine_messages = [
        *history,
        {"role": "user", "content": message, "at": now},
        {
            "role": "assistant",
            "content": draft.cover_letter,
            "screening_answers": answers,
            "warnings": [str(w) for w in outcome.warnings],
            "claims_verified": outcome.claims_verified,
            "at": now,
        },
    ][-MAX_HISTORY:]
    await _capture_fact_candidates(
        db, current_user.id, message, "refine_thread", letter.id,
        context="; ".join(brief.needs) or None,
    )
    await db.commit()

    return CoverLetterRefineResponse(
        cover_letter=draft.cover_letter,
        screening_answers=answers,
        warnings=[str(w) for w in outcome.warnings],
        refine_messages=letter.refine_messages,
        claims_verified=outcome.claims_verified,
    )


CHRIS_REWRITE_THRESHOLD = 0.9  # ≥90% of words changed → treat the submission as Chris's own text


async def _embed_or_none(text: str) -> Optional[List[float]]:
    try:
        return await generate_embedding(text)
    except Exception as exc:
        # Content-free: exception messages can carry user text.
        logger.warning("Embedding failed (%d chars): %s", len(text), type(exc).__name__)
        return None


@router.put("/cover-letters/{letter_id}/final", response_model=CoverLetterFinalResponse)
@limiter.limit("60/hour")
async def submit_final_cover_letter(
    request: Request,
    letter_id: str,
    body: CoverLetterFinalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record what was actually submitted on Upwork → voice sample + fact candidates.

    The voice-sample author is decided here from the edit distance, never by the client.
    Idempotent: resubmitting the same text reuses the proposal row and skips extraction.
    The letter row is locked so concurrent captures (double Submit click) serialize."""
    final_text = body.final_text.strip()
    if not final_text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Final text is empty")

    result = await db.execute(
        select(CoverLetter).where(
            CoverLetter.id == letter_id,
            CoverLetter.user_id == current_user.id,
        ).with_for_update()
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found")

    job = (await db.execute(
        select(Job).where(Job.id == letter.job_id, Job.user_id == current_user.id)
    )).scalar_one_or_none()
    answers = [a.model_dump() for a in (body.final_answers or [])]
    already_captured = letter.final_text == final_text
    edit_pct = word_edit_distance_pct(letter.content, final_text)
    author = "chris" if edit_pct >= CHRIS_REWRITE_THRESHOLD else "chris_edited_ai"
    now = datetime.now(timezone.utc)

    letter.final_text = final_text
    letter.final_answers = answers
    letter.edit_distance_pct = edit_pct
    letter.submitted_text = final_text
    letter.was_submitted = True
    letter.submitted_at = letter.submitted_at or now
    letter.is_final = True

    prop = (await db.execute(
        select(Proposal).where(
            Proposal.user_id == current_user.id,
            Proposal.job_id == letter.job_id,
            Proposal.source == "extension",
        )
    )).scalars().first()
    if prop is None:
        prop = Proposal(
            user_id=current_user.id,
            job_id=letter.job_id,
            cover_letter_text=final_text,
            job_title=job.title if job else None,
            job_skills=(job.skills_required or []) if job else [],
            source="extension",
            status="submitted",
            submitted_at=now,
        )
        db.add(prop)
    # Same meaning as Phase 1 Task 1.8: job_text is the job description only (title lives in job_title)
    job_text = (job.description or None) if job else None
    prop.cover_letter_text = final_text
    prop.author = author
    prop.job_text = job_text
    prop.screening_answers = answers or None  # voice-sample answers (Phase 1 column)
    if not already_captured:
        prop.embedding = await _embed_or_none(final_text)
        if job:
            # Same text shape as Phase 1 Task 1.8 and Phase 2 select_evidence's voice query
            prop.job_needs_embedding = await _embed_or_none(
                "\n\n".join(t for t in (job.title, job.description) if t)
            )
    await db.flush()

    fact_candidates = 0
    if not already_captured:
        qa = "\n\n".join(f"Q: {a['question']}\nA: {a['answer']}" for a in answers if a["answer"])
        fact_candidates = await _capture_fact_candidates(
            db, current_user.id,
            final_text + (f"\n\n{qa}" if qa else ""),
            "upwork_submission", letter.id,
            context=job.title if job else None,
        )
        # Already extracted here, so /facts/from-proposals (Phase 1 Task 1.6) skips this letter
        prop.facts_ingested_at = datetime.now(timezone.utc)
    await db.commit()

    return CoverLetterFinalResponse(
        id=letter.id,
        edit_distance_pct=edit_pct,
        author=author,
        proposal_id=prop.id,
        fact_candidates=fact_candidates,
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
