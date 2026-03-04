"""Proposal endpoints with pgvector semantic search."""
import json
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.embeddings import generate_embedding, get_openai_client
from app.models.user import User
from app.models.proposal import Proposal
from app.models.user import UserProfile
from app.schemas.proposal import (
    ProposalCreate,
    ProposalUpdate,
    ProposalResponse,
    ProposalSearchRequest,
    ProposalSearchResult,
    ProposalBulkCreate,
    ProposalImportFromUpwork,
)

router = APIRouter()


@router.post("", response_model=ProposalResponse, status_code=status.HTTP_201_CREATED)
async def create_proposal(
    data: ProposalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new proposal with embedding."""
    # Generate embedding for the cover letter text
    # Include job context for better semantic matching
    text_for_embedding = data.cover_letter_text
    if data.job_title:
        text_for_embedding = f"Job: {data.job_title}\n\n{text_for_embedding}"

    embedding = await generate_embedding(text_for_embedding)

    proposal = Proposal(
        user_id=current_user.id,
        job_id=data.job_id,
        upwork_proposal_id=data.upwork_proposal_id,
        upwork_job_url=data.upwork_job_url,
        cover_letter_text=data.cover_letter_text,
        job_title=data.job_title,
        job_description_snippet=data.job_description_snippet,
        job_skills=data.job_skills,
        job_budget=data.job_budget,
        job_category=data.job_category,
        bid_amount=data.bid_amount,
        bid_type=data.bid_type,
        status=data.status,
        submitted_at=data.submitted_at,
        source=data.source,
        embedding=embedding,
    )

    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)

    return proposal


@router.get("", response_model=List[ProposalResponse])
async def list_proposals(
    status: Optional[str] = None,
    was_hired: Optional[bool] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's proposals."""
    query = select(Proposal).where(Proposal.user_id == current_user.id)

    if status:
        query = query.where(Proposal.status == status)
    if was_hired is not None:
        query = query.where(Proposal.was_hired == was_hired)
    if source:
        query = query.where(Proposal.source == source)

    query = query.order_by(Proposal.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    proposals = result.scalars().all()

    return proposals


@router.get("/stats")
async def get_proposal_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get proposal statistics."""
    sql = text("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE was_hired = true) as hired,
            COUNT(*) FILTER (WHERE client_responded = true) as responded,
            SUM(earnings) FILTER (WHERE earnings IS NOT NULL) as total_earnings,
            COUNT(*) FILTER (WHERE status = 'submitted') as submitted,
            COUNT(*) FILTER (WHERE status = 'viewed') as viewed
        FROM proposals
        WHERE user_id = :user_id
    """)

    result = await db.execute(sql, {"user_id": current_user.id})
    row = result.fetchone()

    return {
        "total_proposals": row.total or 0,
        "hired": row.hired or 0,
        "responded": row.responded or 0,
        "total_earnings": float(row.total_earnings) if row.total_earnings else 0,
        "submitted": row.submitted or 0,
        "viewed": row.viewed or 0,
        "hire_rate": (row.hired / row.total * 100) if row.total else 0,
        "response_rate": (row.responded / row.total * 100) if row.total else 0,
    }


@router.get("/insights")
async def get_proposal_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Use AI to analyze proposal history and generate actionable insights."""
    # Fetch all proposals
    result = await db.execute(
        select(Proposal)
        .where(Proposal.user_id == current_user.id)
        .order_by(Proposal.submitted_at.desc().nullslast())
    )
    proposals = result.scalars().all()

    if len(proposals) < 3:
        return {"insights": None, "message": "Submit at least 3 proposals to unlock AI insights."}

    # Fetch user profile for context
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    # Build a structured summary for the AI
    status_counts: dict = {}
    for p in proposals:
        s = p.status or "submitted"
        status_counts[s] = status_counts.get(s, 0) + 1

    active_titles = [p.job_title for p in proposals if p.status in ("active", "interview") and p.job_title]
    silent_titles = [p.job_title for p in proposals if p.status == "submitted" and p.job_title]
    hired_titles  = [p.job_title for p in proposals if p.was_hired and p.job_title]

    bid_amounts = [float(p.bid_amount) for p in proposals if p.bid_amount]
    avg_bid = sum(bid_amounts) / len(bid_amounts) if bid_amounts else None

    recent_titles = [p.job_title for p in proposals[:10] if p.job_title]

    profile_summary = ""
    if profile:
        profile_summary = f"""
Freelancer profile:
- Title: {profile.professional_title or 'not set'}
- Skills: {', '.join((profile.skills or [])[:15])}
- Goals: {(profile.career_goals or '')[:200]}
- Preferred rate: {profile.hourly_rate_min or '?'}–{profile.hourly_rate_max or '?'}/hr
""".strip()

    summary = f"""
Proposal history ({len(proposals)} total):
- Status breakdown: {json.dumps(status_counts)}
- Response rate: {round(len(active_titles) / len(proposals) * 100)}% ({len(active_titles)} responses out of {len(proposals)})
- Hired: {len(hired_titles)} times

Job titles that GOT a response ({len(active_titles)}):
{chr(10).join(f'  - {t}' for t in active_titles[:20])}

Job titles that went SILENT ({len(silent_titles)} sample):
{chr(10).join(f'  - {t}' for t in silent_titles[:20])}

{f'Hired for: {chr(10).join(f"  - {t}" for t in hired_titles)}' if hired_titles else ''}

{f'Average bid: ${avg_bid:.0f}/hr' if avg_bid else 'No bid data yet'}

10 most recent applications:
{chr(10).join(f'  - {t}' for t in recent_titles)}

{profile_summary}
""".strip()

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.default_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert Upwork career coach analyzing a freelancer's proposal history. "
                    "Be specific, data-driven, and brutally honest. Focus on what will actually improve results. "
                    "Return a JSON object with these exact keys: "
                    "whats_working (string, 2-3 sentences on patterns in responded/hired proposals), "
                    "whats_not_landing (string, 2-3 sentences on patterns in ignored proposals), "
                    "recommendations (array of 3-5 specific actionable strings), "
                    "job_types_to_target (array of 3-5 job category strings based on response patterns), "
                    "job_types_to_avoid (array of 2-3 job category strings with poor response rates), "
                    "positioning_tip (string, one specific advice about how to position yourself better). "
                    "Be concrete — mention actual job title patterns, not generic advice."
                ),
            },
            {"role": "user", "content": summary},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )

    insights = json.loads(response.choices[0].message.content)
    return {"insights": insights, "proposal_count": len(proposals), "response_rate": round(len(active_titles) / len(proposals) * 100)}


@router.get("/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific proposal."""
    result = await db.execute(
        select(Proposal).where(
            Proposal.id == proposal_id, Proposal.user_id == current_user.id
        )
    )
    proposal = result.scalar_one_or_none()

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposal not found",
        )

    return proposal


@router.put("/{proposal_id}", response_model=ProposalResponse)
async def update_proposal(
    proposal_id: str,
    data: ProposalUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a proposal."""
    result = await db.execute(
        select(Proposal).where(
            Proposal.id == proposal_id, Proposal.user_id == current_user.id
        )
    )
    proposal = result.scalar_one_or_none()

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposal not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Regenerate embedding if cover letter changed
    if "cover_letter_text" in update_data:
        text_for_embedding = update_data["cover_letter_text"]
        if proposal.job_title:
            text_for_embedding = f"Job: {proposal.job_title}\n\n{text_for_embedding}"
        proposal.embedding = await generate_embedding(text_for_embedding)

    for field, value in update_data.items():
        setattr(proposal, field, value)

    await db.commit()
    await db.refresh(proposal)

    return proposal


@router.delete("/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proposal(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a proposal."""
    result = await db.execute(
        select(Proposal).where(
            Proposal.id == proposal_id, Proposal.user_id == current_user.id
        )
    )
    proposal = result.scalar_one_or_none()

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposal not found",
        )

    await db.delete(proposal)
    await db.commit()


@router.post("/search", response_model=List[ProposalSearchResult])
async def search_proposals(
    request: ProposalSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for similar proposals using semantic search."""
    # Generate embedding for the search query
    query_embedding = await generate_embedding(request.query)

    # Build query with optional filtering
    base_sql = """
        SELECT
            id, user_id, job_id, upwork_proposal_id, upwork_job_url,
            cover_letter_text, job_title, job_description_snippet,
            job_skills, job_budget, job_category,
            bid_amount, bid_type, status, was_hired, client_responded,
            earnings, source, submitted_at, created_at, updated_at,
            1 - (embedding <=> CAST(:embedding AS vector)) as similarity
        FROM proposals
        WHERE user_id = :user_id
        AND embedding IS NOT NULL
    """

    if request.include_successful_only:
        base_sql += " AND (was_hired = true OR client_responded = true)"

    base_sql += """
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """

    sql = text(base_sql)

    result = await db.execute(
        sql,
        {
            "embedding": str(query_embedding),
            "user_id": current_user.id,
            "limit": request.limit,
        },
    )

    rows = result.fetchall()

    search_results = []
    for row in rows:
        proposal_response = ProposalResponse(
            id=row.id,
            user_id=row.user_id,
            job_id=row.job_id,
            upwork_proposal_id=row.upwork_proposal_id,
            upwork_job_url=row.upwork_job_url,
            cover_letter_text=row.cover_letter_text,
            job_title=row.job_title,
            job_description_snippet=row.job_description_snippet,
            job_skills=row.job_skills,
            job_budget=row.job_budget,
            job_category=row.job_category,
            bid_amount=float(row.bid_amount) if row.bid_amount else None,
            bid_type=row.bid_type,
            status=row.status,
            was_hired=row.was_hired,
            client_responded=row.client_responded,
            earnings=float(row.earnings) if row.earnings else None,
            source=row.source,
            submitted_at=row.submitted_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

        search_results.append(
            ProposalSearchResult(
                proposal=proposal_response,
                similarity=row.similarity,
            )
        )

    return search_results


@router.post("/bulk", response_model=List[ProposalResponse])
async def bulk_create_proposals(
    request: ProposalBulkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk create proposals (e.g., from import/scrape)."""
    created_proposals = []

    for data in request.proposals:
        # Check if proposal already exists (by upwork_proposal_id)
        if data.upwork_proposal_id:
            existing = await db.execute(
                select(Proposal).where(
                    Proposal.upwork_proposal_id == data.upwork_proposal_id,
                    Proposal.user_id == current_user.id,
                )
            )
            if existing.scalar_one_or_none():
                continue  # Skip duplicates

        # Generate embedding
        text_for_embedding = data.cover_letter_text
        if data.job_title:
            text_for_embedding = f"Job: {data.job_title}\n\n{text_for_embedding}"

        embedding = await generate_embedding(text_for_embedding)

        proposal = Proposal(
            user_id=current_user.id,
            job_id=data.job_id,
            upwork_proposal_id=data.upwork_proposal_id,
            upwork_job_url=data.upwork_job_url,
            cover_letter_text=data.cover_letter_text,
            job_title=data.job_title,
            job_description_snippet=data.job_description_snippet,
            job_skills=data.job_skills,
            job_budget=data.job_budget,
            job_category=data.job_category,
            bid_amount=data.bid_amount,
            bid_type=data.bid_type,
            status=data.status,
            submitted_at=data.submitted_at,
            source=data.source,
            embedding=embedding,
        )

        db.add(proposal)
        created_proposals.append(proposal)

    await db.commit()

    for proposal in created_proposals:
        await db.refresh(proposal)

    return created_proposals


@router.post("/import-from-upwork", response_model=List[ProposalResponse])
async def import_proposals_from_upwork(
    request: ProposalImportFromUpwork,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import proposals scraped from Upwork's 'My Proposals' page."""
    created_proposals = []

    for raw_data in request.proposals:
        # Extract data from scraped format
        upwork_proposal_id = raw_data.get("proposalId")
        cover_letter_text = raw_data.get("coverLetter", "")
        job_title = raw_data.get("jobTitle")
        job_url = raw_data.get("jobUrl")
        bid_amount = raw_data.get("bidAmount")
        bid_type = raw_data.get("bidType")
        status_str = raw_data.get("status", "submitted")
        submitted_at_str = raw_data.get("submittedAt")

        # Require at least a job title to import
        if not job_title:
            continue

        # Check for duplicate
        if upwork_proposal_id:
            existing = await db.execute(
                select(Proposal).where(
                    Proposal.upwork_proposal_id == upwork_proposal_id,
                    Proposal.user_id == current_user.id,
                )
            )
            if existing.scalar_one_or_none():
                continue

        # Parse submitted_at — try ISO first, then "Mar 3, 2026" format
        submitted_at = None
        if submitted_at_str:
            try:
                submitted_at = datetime.fromisoformat(submitted_at_str.replace("Z", "+00:00"))
            except Exception:
                try:
                    submitted_at = datetime.strptime(submitted_at_str, "%b %d, %Y")
                except Exception:
                    pass

        # Generate embedding from whatever text is available
        text_for_embedding = cover_letter_text or ""
        if job_title:
            text_for_embedding = f"Job: {job_title}\n\n{text_for_embedding}".strip()

        embedding = await generate_embedding(text_for_embedding) if text_for_embedding else None

        client_responded = status_str in ("responded", "interviewed", "hired")
        was_hired = status_str == "hired"

        proposal = Proposal(
            user_id=current_user.id,
            upwork_proposal_id=upwork_proposal_id,
            upwork_job_url=job_url,
            cover_letter_text=cover_letter_text or "",
            job_title=job_title,
            bid_amount=bid_amount,
            bid_type=bid_type,
            status=status_str,
            client_responded=client_responded,
            was_hired=was_hired,
            submitted_at=submitted_at,
            source="scraped",
            embedding=embedding,
        )

        db.add(proposal)
        created_proposals.append(proposal)

    await db.commit()

    for proposal in created_proposals:
        await db.refresh(proposal)

    return created_proposals
