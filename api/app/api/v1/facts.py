"""Facts (knowledge layer) endpoints: review queue, manual facts, ingestion."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.embeddings import generate_embedding
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.models.fact import Fact
from app.models.job import Job
from app.models.memory import Memory
from app.models.proposal import Proposal
from app.models.user import User
from app.schemas.fact import (
    MAX_INGEST_TEXT,
    FactBulkApprove,
    FactCandidate,
    FactCreate,
    FactIngestItem,
    FactIngestRequest,
    FactIngestResult,
    FactKind,
    FactOut,
    FactStatus,
    FactUpdate,
)
from app.services.facts import MAX_ITEMS_PER_RUN, fact_embedding_text, ingest_items, upsert_manual_fact

router = APIRouter()


@router.get("", response_model=List[FactOut])
async def list_facts(
    status_filter: Optional[FactStatus] = Query(None, alias="status"),
    kind: Optional[FactKind] = None,
    limit: int = Query(500, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List facts for review (grouped client-side by kind)."""
    query = select(Fact).where(Fact.user_id == current_user.id)
    if status_filter:
        query = query.where(Fact.status == status_filter)
    if kind:
        query = query.where(Fact.kind == kind)
    query = query.order_by(Fact.kind, Fact.strength.desc(), Fact.created_at.desc()).limit(limit)
    return (await db.execute(query)).scalars().all()


@router.post("", response_model=FactOut, status_code=status.HTTP_201_CREATED)
async def create_fact(
    data: FactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a manual fact. The user typed it, so it is approved; a near-duplicate is
    corrected to the user's wording rather than kept."""
    cand = FactCandidate(source_type="manual", **data.model_dump())
    fact = await upsert_manual_fact(db, current_user.id, cand)
    await db.commit()
    await db.refresh(fact)
    return fact


@router.patch("/{fact_id}", response_model=FactOut)
async def update_fact(
    fact_id: str,
    data: FactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit / approve / reject a fact."""
    fact = (await db.execute(
        select(Fact).where(Fact.id == fact_id, Fact.user_id == current_user.id)
    )).scalar_one_or_none()
    if not fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    # Only `detail` is nullable; an explicit null elsewhere is ignored rather than a 500.
    update_data = {
        k: v for k, v in data.model_dump(exclude_unset=True).items()
        if v is not None or k == "detail"
    }
    for field, value in update_data.items():
        setattr(fact, field, value)
    if "statement" in update_data or "detail" in update_data:
        fact.embedding = await generate_embedding(fact_embedding_text(fact.statement, fact.detail))

    await db.commit()
    await db.refresh(fact)
    return fact


@router.post("/bulk-approve")
async def bulk_approve_facts(
    request: FactBulkApprove,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not request.ids:
        return {"approved": 0}
    result = await db.execute(
        update(Fact)
        .where(Fact.user_id == current_user.id, Fact.id.in_(request.ids))
        .values(status="approved")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return {"approved": result.rowcount}


@router.post("/ingest", response_model=FactIngestResult)
@limiter.limit("120/hour")
async def ingest_facts(
    request: Request,
    body: FactIngestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract fact candidates from user-written text (used by scripts/ingest_chatgpt_facts.py).

    Ingested text can quote clients and job posts, so `body.auto_approve` is not honoured:
    new candidates always go to review; only a match to an approved fact is auto-approved (§1.7)."""
    counts = await ingest_items(db, current_user.id, body.source_type, body.items)
    await db.commit()
    return FactIngestResult(**counts)


@router.post("/from-memories", response_model=FactIngestResult)
@limiter.limit("10/hour")
async def facts_from_memories(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Split curated bio memories into atomic facts, auto-approved (spec §1.3.4).
    Processes MAX_ITEMS_PER_RUN memories per call; call again while remaining > 0."""
    memories = (await db.execute(
        select(Memory).where(
            Memory.user_id == current_user.id,
            Memory.exclude_from_retrieval.is_(False),
            Memory.importance_score >= 0.9,
            ~Memory.content.like("JOB POSTING:%"),
            or_(Memory.category.is_(None), Memory.category != "lesson"),
        )
    )).scalars().all()
    items = [
        FactIngestItem(
            text=(f"{m.title}\n{m.content}" + (f"\nOutcome: {m.outcome}" if m.outcome else ""))[:MAX_INGEST_TEXT],
            source_ref=m.id,
        )
        for m in memories
    ]
    counts = await ingest_items(
        db, current_user.id, "bio_memory", items, auto_approve=True, max_items=MAX_ITEMS_PER_RUN
    )
    await db.commit()
    return FactIngestResult(**counts)


def _proposal_source_text(p: Proposal) -> str:
    parts = [p.cover_letter_text.strip()]
    for qa in p.screening_answers or []:
        parts.append(f"Q: {qa.get('question', '')}\nA: {qa.get('answer', '')}")
    return "\n\n".join(parts)[:MAX_INGEST_TEXT]


@router.post("/from-proposals", response_model=FactIngestResult)
@limiter.limit("60/hour")
async def facts_from_proposals(
    request: Request,
    limit: int = Query(10, ge=1, le=25),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fact candidates from submitted letters + answers (spec §1.3.2). Call repeatedly until remaining == 0."""
    pending = (await db.execute(
        select(Proposal)
        .where(
            Proposal.user_id == current_user.id,
            Proposal.author.in_(("chris", "chris_edited_ai")),
            Proposal.cover_letter_text != "",
            Proposal.facts_ingested_at.is_(None),
        )
        .order_by(Proposal.submitted_at.desc().nullslast(), Proposal.created_at.desc())
    )).scalars().all()
    batch = pending[:limit]

    items = [
        FactIngestItem(
            text=_proposal_source_text(p),
            source_ref=p.id,
            context=f"Job: {p.job_title or ''}\n{(p.job_text or '')[:1500]}".strip(),
        )
        for p in batch
    ]
    counts = await ingest_items(db, current_user.id, "upwork_proposal", items)
    retry = set(counts["retry_refs"])
    counts.pop("remaining")
    now = datetime.now(timezone.utc)
    for p in batch:
        if p.id not in retry:
            # zero-fact letters and given-up failures too, so the queue always advances
            p.facts_ingested_at = now
    await db.commit()
    return FactIngestResult(**counts, remaining=len(pending) - len(batch) + len(retry))


@router.post("/from-contracts", response_model=FactIngestResult)
@limiter.limit("10/hour")
async def facts_from_contracts(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fact candidates from imported Upwork contracts (spec §1.3.3). Never auto-approved.
    Processes MAX_ITEMS_PER_RUN unprocessed contracts per call; call again while remaining > 0."""
    jobs = (await db.execute(
        select(Job)
        .where(
            Job.user_id == current_user.id,
            Job.source == "contract_import",
            Job.upwork_job_id.is_not(None),
        )
        .order_by(Job.created_at.desc())
    )).scalars().all()
    items = [
        FactIngestItem(text=(j.description or j.title)[:MAX_INGEST_TEXT], source_ref=j.upwork_job_id)
        for j in jobs
    ]
    counts = await ingest_items(db, current_user.id, "upwork_contract", items, max_items=MAX_ITEMS_PER_RUN)
    await db.commit()
    return FactIngestResult(**counts)
