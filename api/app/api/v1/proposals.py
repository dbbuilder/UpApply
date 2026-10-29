"""Proposal endpoints with pgvector semantic search."""
import json
import logging
import re
from typing import List, Optional
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.embeddings import generate_embedding, get_openai_client
from app.core.rate_limit import limiter
from app.models.cover_letter import CoverLetter
from app.models.job import Job
from app.models.user import User
from app.models.proposal import PENDING_PROPOSAL_STATUSES, Proposal
from app.models.user import UserProfile
from app.schemas.proposal import (
    ProposalCreate,
    ProposalUpdate,
    ProposalResponse,
    ProposalSearchRequest,
    ProposalSearchResult,
    ProposalBulkCreate,
    ProposalImportFromUpwork,
    ProposalOutcomeItem,
    ProposalOutcomeSyncRequest,
    ProposalOutcomeSyncResponse,
)
from app.services.outcomes import apply_outcome, parse_submitted_at, resolve_outcome
from app.services.proposal_status import advance_status

router = APIRouter()
logger = logging.getLogger(__name__)


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
        was_hired=data.was_hired,
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
    job_url: Optional[str] = None,
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
    if job_url:
        import re as _re
        uid_m = _re.search(r'~[0-9a-f]+', job_url, _re.IGNORECASE)
        if uid_m:
            query = query.where(Proposal.upwork_job_url.contains(uid_m.group(0)))

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
    """Get proposal statistics including funnel metrics."""
    sql = text("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE was_hired = true) as hired,
            COUNT(*) FILTER (WHERE client_responded = true) as responded,
            COUNT(*) FILTER (WHERE status = 'interviewed') as interviewed,
            COUNT(*) FILTER (WHERE status = 'submitted') as submitted,
            COUNT(*) FILTER (WHERE status = 'viewed') as viewed,
            SUM(earnings) FILTER (WHERE earnings IS NOT NULL) as total_earnings,
            AVG(
                EXTRACT(EPOCH FROM (updated_at - submitted_at)) / 86400.0
            ) FILTER (WHERE client_responded = true AND submitted_at IS NOT NULL) as avg_days_to_response
        FROM proposals
        WHERE user_id = :user_id
    """)

    result = await db.execute(sql, {"user_id": current_user.id})
    row = result.fetchone()

    # Get scored count from job_reviews (top of funnel)
    scored_sql = text("SELECT COUNT(*) as cnt FROM job_reviews WHERE user_id = :user_id")
    scored_result = await db.execute(scored_sql, {"user_id": current_user.id})
    scored_row = scored_result.fetchone()
    scored_count = scored_row.cnt or 0

    total = row.total or 0
    hired = row.hired or 0
    responded = row.responded or 0

    return {
        "total_proposals": total,
        "hired": hired,
        "responded": responded,
        "interviewed": row.interviewed or 0,
        "total_earnings": float(row.total_earnings) if row.total_earnings else 0,
        "submitted": row.submitted or 0,
        "viewed": row.viewed or 0,
        "scored_count": scored_count,
        "hire_rate": (hired / total * 100) if total else 0,
        "response_rate": (responded / total * 100) if total else 0,
        "avg_days_to_response": round(float(row.avg_days_to_response), 1) if row.avg_days_to_response else None,
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
- Skills: {', '.join(s.get('name', str(s)) if isinstance(s, dict) else str(s) for s in (profile.skills or [])[:15])}
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


TITLE_MATCH_WINDOW = timedelta(days=1)  # Upwork shows a local date; allow for the timezone skew


def _title_day_key(job_title: Optional[str], submitted_at: Optional[str]) -> Optional[tuple]:
    """(title, submit day) used by the title fallback; None when either is missing."""
    day = parse_submitted_at(submitted_at)
    if not job_title or day is None:
        return None
    return (job_title, day.date())


def _ambiguous_title_days(keys) -> set:
    """Title+day keys seen more than once in one batch: those rows cannot be told apart."""
    counts = Counter(k for k in keys if k is not None)
    return {k for k, n in counts.items() if n > 1}


async def _find_proposal_for_outcome(
    db: AsyncSession, user_id: str, item: ProposalOutcomeItem, ambiguous: frozenset | set = frozenset()
) -> Optional[Proposal]:
    """Match by internal id, then Upwork id, then a click-captured proposal lacking an Upwork id.

    The title fallback only binds when the title AND the submit day (±1 day) match exactly one
    click-captured row, and no other item in the batch shares that title and day. Generic
    titles are common, and a wrong bind would credit the wrong letter's facts permanently."""
    if item.proposal_id:
        return (await db.execute(
            select(Proposal).where(Proposal.id == item.proposal_id, Proposal.user_id == user_id)
        )).scalar_one_or_none()
    if not item.upwork_proposal_id:
        return None
    prop = (await db.execute(
        select(Proposal).where(
            Proposal.upwork_proposal_id == item.upwork_proposal_id,
            Proposal.user_id == user_id,
        )
    )).scalar_one_or_none()
    key = _title_day_key(item.job_title, item.submitted_at)
    if prop or key is None or key in ambiguous:
        return prop
    day_start = datetime(key[1].year, key[1].month, key[1].day, tzinfo=timezone.utc)
    candidates = (await db.execute(
        select(Proposal)
        .where(
            Proposal.user_id == user_id,
            Proposal.upwork_proposal_id.is_(None),
            Proposal.source == "extension",  # only click-captured rows (Task 3.4), never chatgpt_import
            Proposal.job_title == item.job_title,
            Proposal.submitted_at >= day_start - TITLE_MATCH_WINDOW,
            Proposal.submitted_at < day_start + timedelta(days=1) + TITLE_MATCH_WINDOW,
        )
        .limit(2)
        # Lock the row until commit: a concurrent sync (another Proposals tab) that read it
        # unbound would otherwise overwrite this bind. A waiter re-checks the IS NULL filter
        # after the lock is released, so it finds nothing instead of rebinding.
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalars().all()
    return candidates[0] if len(candidates) == 1 else None


@router.post("/outcomes", response_model=ProposalOutcomeSyncResponse)
@limiter.limit("60/hour")
async def sync_proposal_outcomes(
    request: Request,
    body: ProposalOutcomeSyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk status sync from the Proposals page → proposals.outcome; credit facts on wins."""
    updated = credited = not_found = 0
    ambiguous = _ambiguous_title_days(_title_day_key(i.job_title, i.submitted_at) for i in body.items)
    for item in body.items:
        prop = await _find_proposal_for_outcome(db, current_user.id, item, ambiguous)
        if prop is None:
            not_found += 1
            continue
        if item.upwork_proposal_id and not prop.upwork_proposal_id:
            prop.upwork_proposal_id = item.upwork_proposal_id
        if prop.submitted_at is None:
            prop.submitted_at = parse_submitted_at(item.submitted_at)
        before = prop.outcome
        advance_status(prop, item.status, "outcome_sync")  # stage moves forward only
        outcome = resolve_outcome(item.status, prop.submitted_at or prop.created_at)
        if await apply_outcome(db, prop, outcome):
            credited += 1
        if prop.outcome != before:
            updated += 1
    await db.commit()
    return ProposalOutcomeSyncResponse(updated=updated, credited=credited, not_found=not_found)


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


VOICE_OUTCOMES = {"no_response", "viewed", "replied", "interviewed", "hired", "declined"}
MAX_JOB_TEXT_CHARS = 20_000
MAX_COVER_LETTER_CHARS = 20_000
MAX_JOB_TITLE_CHARS = 500
MAX_SCREENING_ANSWERS = 50
MAX_ANSWER_CHARS = 5_000


def _derive_outcome(raw_outcome: Optional[str], status_str: Optional[str], was_hired: Optional[bool]) -> Optional[str]:
    """Map scraper status onto the voice-sample outcome enum (None = unknown yet)."""
    if raw_outcome in VOICE_OUTCOMES:
        return raw_outcome
    if was_hired:
        return "hired"
    s = (status_str or "").lower()
    if "interview" in s:
        return "interviewed"
    if s in ("responded", "active"):
        return "replied"
    if "declin" in s:
        return "declined"
    if s == "viewed":
        return "viewed"
    return None


_UPWORK_JOB_SLUG = re.compile(r"~(0[0-9a-zA-Z]+)")
_WORD = re.compile(r"[a-z0-9]+")
LETTER_IS_JOB_JACCARD = 0.8
MIN_CONTAINED_CHARS = 50


def _normalized(text_: str) -> str:
    return " ".join(_WORD.findall(text_.lower()))


def _letter_is_job_description(letter: str, job_text: Optional[str]) -> bool:
    """A scraped 'cover letter' that is really the job post (scraper picked the wrong node)."""
    if not letter or not job_text:
        return False
    a, b = _normalized(letter), _normalized(job_text)
    if not a or not b:
        return False
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= MIN_CONTAINED_CHARS and shorter in longer:
        return True
    ta, tb = set(a.split()), set(b.split())
    return len(ta & tb) / len(ta | tb) > LETTER_IS_JOB_JACCARD


async def _server_author(db: AsyncSession, user_id: str, job_url: Optional[str], job_title: str) -> str:
    """'chris_edited_ai' when UpApply generated a letter for this user's matching job, else 'chris'.
    Never taken from the client."""
    conds = [func.lower(func.trim(Job.title)) == job_title.strip().lower()]
    if job_url:
        conds.append(Job.upwork_url == job_url)
        slug = _UPWORK_JOB_SLUG.search(job_url)
        if slug:
            conds.append(Job.upwork_job_id.in_([slug.group(1), f"~{slug.group(1)}"]))
            conds.append(Job.upwork_url.contains(f"~{slug.group(1)}"))
    hit = (await db.execute(
        select(CoverLetter.id)
        .join(Job, CoverLetter.job_id == Job.id)
        .where(CoverLetter.user_id == user_id, Job.user_id == user_id, or_(*conds))
        .limit(1)
    )).first()
    return "chris_edited_ai" if hit else "chris"


def _clean_answers(raw) -> Optional[list]:
    if not isinstance(raw, list):
        return None
    answers = [
        {
            "question": str(a.get("question") or "").strip()[:MAX_ANSWER_CHARS],
            "answer": str(a.get("answer") or "").strip()[:MAX_ANSWER_CHARS],
        }
        for a in raw
        if isinstance(a, dict) and str(a.get("answer") or "").strip()
    ]
    return answers[:MAX_SCREENING_ANSWERS] or None


async def _job_needs_embedding(job_title: Optional[str], job_text: Optional[str]) -> Optional[List[float]]:
    """Embedding of the JOB (not the letter) so voice-sample retrieval is job<->job."""
    text_for_embedding = "\n\n".join(t for t in (job_title, job_text) if t)
    if not text_for_embedding:
        return None
    try:
        return await generate_embedding(text_for_embedding)
    except Exception:
        return None


@router.post("/import-from-upwork", response_model=List[ProposalResponse])
async def import_proposals_from_upwork(
    request: ProposalImportFromUpwork,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import proposals scraped from Upwork (list + detail pages) as voice samples.

    New rows are created; existing rows (same proposalId) are backfilled with the full
    letter, screening answers, job text and the latest outcome. Returns created rows only.
    """
    created_proposals = []
    skipped = 0
    ambiguous = _ambiguous_title_days(
        _title_day_key(str(r.get("jobTitle") or "").strip()[:MAX_JOB_TITLE_CHARS] or None,
                       str(r.get("submittedAt") or "")[:50] or None)
        for r in request.proposals if isinstance(r, dict)
    )

    for raw_data in request.proposals:
        upwork_proposal_id = raw_data.get("proposalId")
        cover_letter_text = (raw_data.get("coverLetter") or "").strip()[:MAX_COVER_LETTER_CHARS]
        job_title = str(raw_data.get("jobTitle") or "").strip()[:MAX_JOB_TITLE_CHARS] or None
        job_url = raw_data.get("jobUrl")
        bid_amount = raw_data.get("bidAmount")
        bid_type = raw_data.get("bidType")
        status_str = raw_data.get("status", "submitted")
        status_key = (status_str or "").strip().lower()  # scraped statuses arrive capitalised
        submitted_at_str = raw_data.get("submittedAt")
        screening_answers = _clean_answers(raw_data.get("screeningAnswers"))
        job_text = (raw_data.get("jobDescription") or "").strip()[:MAX_JOB_TEXT_CHARS] or None
        # Require at least a job title to import
        if not job_title:
            continue
        letter_is_job = _letter_is_job_description(cover_letter_text, job_text)

        # Allow explicit wasHired override from the scraper (e.g. archived proposals
        # whose status string doesn't say "hired" but the scraper detected a contract)
        was_hired_override = raw_data.get("wasHired")
        if was_hired_override is not None:
            was_hired = bool(was_hired_override)
        elif status_key == "hired":
            was_hired = True
        elif status_key in PENDING_PROPOSAL_STATUSES:
            was_hired = None  # outcome still open, not declined
        else:
            was_hired = False
        outcome = _derive_outcome(raw_data.get("outcome"), status_str, was_hired)

        if upwork_proposal_id:
            # Upwork id first, then the newest click-captured row (Task 3.4) with the same title
            existing = await _find_proposal_for_outcome(
                db, current_user.id,
                ProposalOutcomeItem(
                    upwork_proposal_id=str(upwork_proposal_id)[:100], job_title=job_title,
                    status=str(status_str or "submitted")[:50],
                    submitted_at=str(submitted_at_str or "")[:50] or None,
                ),
                ambiguous,
            )
            if existing:
                if not existing.upwork_proposal_id:
                    existing.upwork_proposal_id = upwork_proposal_id
                if letter_is_job or _letter_is_job_description(cover_letter_text, existing.job_text):
                    # The scraped "letter" is the job post: never store it as the user's letter,
                    # but still apply the outcome / job text / screening-answer updates below.
                    skipped += 1
                    cover_letter_text = ""
                if cover_letter_text and len(cover_letter_text) > len(existing.cover_letter_text or ""):
                    existing.cover_letter_text = cover_letter_text
                    try:
                        existing.embedding = await generate_embedding(f"Job: {job_title}\n\n{cover_letter_text}")
                    except Exception:
                        # Keep the previous embedding; one embedding failure must not roll back the batch.
                        logger.warning("Letter re-embed failed for proposal %s", existing.id, exc_info=True)
                    existing.facts_ingested_at = None  # new text -> eligible for /facts/from-proposals again
                if screening_answers and screening_answers != existing.screening_answers:
                    existing.screening_answers = screening_answers
                    existing.facts_ingested_at = None
                if job_text and not existing.job_text:
                    existing.job_text = job_text
                    # Replace a title-only job embedding now that the job text is known.
                    existing.job_needs_embedding = await _job_needs_embedding(job_title, job_text)
                elif existing.job_needs_embedding is None:
                    existing.job_needs_embedding = await _job_needs_embedding(job_title, existing.job_text)
                advance_status(existing, status_str, "upwork_import")
                if outcome:
                    await apply_outcome(db, existing, outcome)  # forward-only; credits facts once
                continue

        if letter_is_job:
            skipped += 1
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

        # Letter embedding (legacy search) + job embedding (voice-sample retrieval)
        text_for_embedding = f"Job: {job_title}\n\n{cover_letter_text}".strip()
        embedding = await generate_embedding(text_for_embedding)

        proposal = Proposal(
            user_id=current_user.id,
            upwork_proposal_id=upwork_proposal_id,
            upwork_job_url=job_url,
            cover_letter_text=cover_letter_text,
            job_title=job_title,
            bid_amount=bid_amount,
            bid_type=bid_type,
            status=status_str,
            client_responded=status_key in ("responded", "interviewed", "hired"),
            was_hired=was_hired,
            submitted_at=submitted_at,
            source="scraped",
            embedding=embedding,
            author=await _server_author(db, current_user.id, job_url, job_title),
            outcome=outcome,
            job_text=job_text,
            screening_answers=screening_answers,
            job_needs_embedding=await _job_needs_embedding(job_title, job_text),
        )

        db.add(proposal)
        created_proposals.append(proposal)

    await db.commit()
    if skipped:
        logger.info("import-from-upwork skipped %d letter(s) matching their job description", skipped)

    for proposal in created_proposals:
        await db.refresh(proposal)

    return created_proposals


@router.post("/backfill-job-embeddings")
@limiter.limit("10/hour")
async def backfill_job_embeddings(
    request: Request,
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fill job_needs_embedding on the caller's voice-sample rows (author != 'ai') that lack it,
    from job_text, the linked job's description, or the stored snippet. Call again while
    remaining > 0."""
    missing = (
        select(Proposal, Job)
        .outerjoin(Job, (Job.id == Proposal.job_id) & (Job.user_id == current_user.id))
        .where(
            Proposal.user_id == current_user.id,
            Proposal.author != "ai",
            Proposal.job_needs_embedding.is_(None),
        )
    )
    total = (await db.execute(select(func.count()).select_from(missing.subquery()))).scalar_one()
    rows = (await db.execute(missing.order_by(Proposal.created_at.desc()).limit(limit))).all()
    embedded = 0
    for proposal, job in rows:
        title = proposal.job_title or (job.title if job else None)
        text_ = proposal.job_text or (job.description if job else None) or proposal.job_description_snippet
        vector = await _job_needs_embedding(title, text_)
        if vector is not None:
            proposal.job_needs_embedding = vector
            embedded += 1
    await db.commit()
    return {"embedded": embedded, "remaining": max(total - len(rows), 0)}
