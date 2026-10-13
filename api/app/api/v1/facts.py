"""Facts (knowledge layer) endpoints: review queue, manual facts, ingestion."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.embeddings import generate_embedding
from app.core.security import get_current_user
from app.models.fact import Fact
from app.models.user import User
from app.schemas.fact import (
    FactBulkApprove,
    FactCandidate,
    FactCreate,
    FactKind,
    FactOut,
    FactStatus,
    FactUpdate,
)
from app.services.facts import fact_embedding_text, upsert_manual_fact

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
