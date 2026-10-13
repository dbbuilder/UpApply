"""Facts (knowledge layer) endpoints: review queue, manual facts, ingestion."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.embeddings import generate_embedding
from app.core.security import get_current_user
from app.models.fact import Fact
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
from app.services.facts import fact_embedding_text, ingest_items, upsert_manual_fact

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
async def ingest_facts(
    request: FactIngestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract fact candidates from user-written text (used by scripts/ingest_chatgpt_facts.py).

    Ingested text can quote clients and job posts, so `request.auto_approve` is not honoured:
    new candidates always go to review; only a match to an approved fact is auto-approved (§1.7)."""
    counts = await ingest_items(db, current_user.id, request.source_type, request.items)
    await db.commit()
    return FactIngestResult(**counts)


@router.post("/from-memories", response_model=FactIngestResult)
async def facts_from_memories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Split curated bio memories into atomic facts, auto-approved (spec §1.3.4)."""
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
    counts = await ingest_items(db, current_user.id, "bio_memory", items, auto_approve=True)
    await db.commit()
    return FactIngestResult(**counts)


def _proposal_source_text(p: Proposal) -> str:
    parts = [p.cover_letter_text.strip()]
    for qa in p.screening_answers or []:
        parts.append(f"Q: {qa.get('question', '')}\nA: {qa.get('answer', '')}")
    return "\n\n".join(parts)[:MAX_INGEST_TEXT]


@router.post("/from-proposals", response_model=FactIngestResult)
async def facts_from_proposals(
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
    failed = set(counts["failed_refs"])
    now = datetime.now(timezone.utc)
    for p in batch:
        if p.id not in failed:
            p.facts_ingested_at = now  # zero-fact letters too, so the next call moves on
    await db.commit()
    return FactIngestResult(**counts, remaining=len(pending) - len(batch) + len(failed))
