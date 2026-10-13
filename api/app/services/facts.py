"""Fact store: embedding, dedupe/merge, auto-approve, semantic search, outcome crediting.

Nothing here commits — callers own the transaction (routers commit; get_db commits too).
"""
from typing import List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import generate_embedding
from app.models.fact import Fact
from app.schemas.fact import FactCandidate

DEDUPE_THRESHOLD = 0.92


def fact_embedding_text(statement: str, detail: Optional[str]) -> str:
    """Facts embed statement + detail only (spec §1.2)."""
    return f"{statement}\n{detail}" if detail else statement


def _union(existing: Optional[List[str]], new: Optional[List[str]]) -> List[str]:
    return list(dict.fromkeys([*(existing or []), *(new or [])]))


def _source_entry(cand: FactCandidate) -> dict:
    return {
        "source_type": cand.source_type,
        "source_ref": cand.source_ref,
        "snippet": cand.source_snippet,
    }


async def _nearest(
    db: AsyncSession, user_id: str, embedding: List[float]
) -> Optional[Tuple[Fact, float]]:
    distance = Fact.embedding.cosine_distance(embedding)
    row = (await db.execute(
        select(Fact, (1 - distance).label("similarity"))
        .where(Fact.user_id == user_id, Fact.embedding.is_not(None))
        .order_by(distance)
        .limit(1)
    )).first()
    return (row[0], float(row[1])) if row else None


async def upsert_candidate_outcome(
    db: AsyncSession,
    user_id: str,
    cand: FactCandidate,
    auto_approve: bool = False,
) -> Tuple[Fact, str]:
    """Insert or merge one candidate; returns (fact, 'created' | 'merged' | 'auto_approved')."""
    embedding = await generate_embedding(fact_embedding_text(cand.statement, cand.detail))
    nearest = await _nearest(db, user_id, embedding)

    if nearest and nearest[1] >= DEDUPE_THRESHOLD:
        fact = nearest[0]
        fact.sources = [*(fact.sources or []), _source_entry(cand)]
        fact.skills = _union(fact.skills, cand.skills)
        fact.industries = _union(fact.industries, cand.industries)
        fact.job_types = _union(fact.job_types, list(cand.job_types))
        if fact.status != "approved" and cand.strength > fact.strength:
            # Unreviewed fact: keep the strongest wording. Approved wording is never touched.
            fact.statement = cand.statement
            fact.detail = cand.detail
            fact.embedding = embedding
        fact.strength = max(fact.strength, cand.strength)
        if auto_approve and fact.status == "candidate":
            fact.status = "approved"
        await db.flush()
        return fact, ("auto_approved" if fact.status == "approved" else "merged")

    fact = Fact(
        user_id=user_id,
        kind=cand.kind,
        statement=cand.statement,
        detail=cand.detail,
        skills=list(cand.skills),
        industries=list(cand.industries),
        job_types=list(cand.job_types),
        strength=cand.strength,
        status="approved" if auto_approve else "candidate",
        source_type=cand.source_type,
        source_ref=cand.source_ref,
        sources=[_source_entry(cand)],
        embedding=embedding,
    )
    db.add(fact)
    await db.flush()
    return fact, ("auto_approved" if auto_approve else "created")


async def upsert_candidate(
    db: AsyncSession,
    user_id: str,
    cand: FactCandidate,
    auto_approve: bool = False,
) -> Fact:
    fact, _ = await upsert_candidate_outcome(db, user_id, cand, auto_approve)
    return fact


async def search_facts(
    db: AsyncSession,
    user_id: str,
    query_embedding: List[float],
    limit: int = 8,
    status: str = "approved",
) -> List[Tuple[Fact, float]]:
    """Nearest facts by cosine similarity, most similar first."""
    distance = Fact.embedding.cosine_distance(query_embedding)
    rows = (await db.execute(
        select(Fact, (1 - distance).label("similarity"))
        .where(Fact.user_id == user_id, Fact.status == status, Fact.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )).all()
    return [(row[0], float(row[1])) for row in rows]


async def credit_facts(
    db: AsyncSession, fact_ids: List[str], won: bool, *, user_id: str
) -> None:
    """won=False: the facts were used in a generated draft (times_used += 1).
    won=True: that draft got a reply/interview/hire (times_in_won += 1).

    Scoped to user_id: ids belonging to another user are ignored."""
    if not fact_ids:
        return
    ids = [str(i) for i in fact_ids]
    stmt = update(Fact).where(Fact.id.in_(ids), Fact.user_id == user_id)
    if won:
        stmt = stmt.values(times_in_won=Fact.times_in_won + 1)
    else:
        stmt = stmt.values(times_used=Fact.times_used + 1)
    await db.execute(stmt.execution_options(synchronize_session=False))
