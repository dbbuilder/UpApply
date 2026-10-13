"""Fact store: embedding, dedupe/merge, auto-approve, semantic search, outcome crediting.

Nothing here commits — callers own the transaction (routers commit; get_db commits too).
"""
import asyncio
import logging
from typing import List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import generate_embedding
from app.models.fact import Fact
from app.schemas.fact import FactCandidate, FactIngestItem
from app.services.fact_extraction import extract_facts

logger = logging.getLogger(__name__)

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


async def upsert_manual_fact(db: AsyncSession, user_id: str, cand: FactCandidate) -> Fact:
    """A fact the user typed: always approved, and the user's wording always wins.

    A near-duplicate (>= DEDUPE_THRESHOLD) is corrected in place — statement, detail, kind and
    embedding are overwritten — so a rejected or extracted candidate's old wording is never
    promoted to approved. Otherwise a new approved fact is created."""
    cand = cand.model_copy(update={"source_snippet": cand.source_snippet or cand.statement})
    embedding = await generate_embedding(fact_embedding_text(cand.statement, cand.detail))
    nearest = await _nearest(db, user_id, embedding)

    if not (nearest and nearest[1] >= DEDUPE_THRESHOLD):
        fact = Fact(
            user_id=user_id,
            kind=cand.kind,
            statement=cand.statement,
            detail=cand.detail,
            skills=list(cand.skills),
            industries=list(cand.industries),
            job_types=list(cand.job_types),
            strength=cand.strength,
            status="approved",
            source_type=cand.source_type,
            source_ref=cand.source_ref,
            sources=[_source_entry(cand)],
            embedding=embedding,
        )
        db.add(fact)
        await db.flush()
        return fact

    fact = nearest[0]
    fact.kind = cand.kind
    fact.statement = cand.statement
    fact.detail = cand.detail
    fact.embedding = embedding
    fact.sources = [*(fact.sources or []), _source_entry(cand)]
    fact.skills = _union(fact.skills, cand.skills)
    fact.industries = _union(fact.industries, cand.industries)
    fact.job_types = _union(fact.job_types, list(cand.job_types))
    fact.strength = max(fact.strength, cand.strength)
    fact.status = "approved"
    await db.flush()
    return fact


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


async def _already_ingested(db: AsyncSession, user_id: str, source_type: str, source_ref: str) -> bool:
    row = await db.execute(
        select(Fact.id)
        .where(
            Fact.user_id == user_id,
            Fact.sources.contains([{"source_type": source_type, "source_ref": source_ref}]),
        )
        .limit(1)
    )
    return row.first() is not None


async def ingest_items(
    db: AsyncSession,
    user_id: str,
    source_type: str,
    items: List[FactIngestItem],
    auto_approve: bool = False,
) -> dict:
    """Extract candidates from each item and upsert them. Items whose source_ref already
    appears in a fact's sources are skipped, so re-runs only pay for new material."""
    counts = {"created": 0, "merged": 0, "auto_approved": 0, "skipped": 0, "failed": 0}
    failed_refs: List[Optional[str]] = []

    pending: List[FactIngestItem] = []
    for item in items:
        if item.source_ref and await _already_ingested(db, user_id, source_type, item.source_ref):
            counts["skipped"] += 1
        else:
            pending.append(item)

    results = await asyncio.gather(
        *(extract_facts(i.text, source_type, i.source_ref, i.context) for i in pending),
        return_exceptions=True,
    )
    for item, result in zip(pending, results):
        if isinstance(result, BaseException):
            logger.warning("Fact extraction failed for %s/%s: %s", source_type, item.source_ref, result)
            counts["failed"] += 1
            failed_refs.append(item.source_ref)
            continue
        for cand in result:
            _, outcome = await upsert_candidate_outcome(db, user_id, cand, auto_approve)
            counts[outcome] += 1
    # Not a FactIngestResult field (pydantic ignores it); /from-proposals uses it to leave
    # failed letters unmarked so they are retried.
    counts["failed_refs"] = failed_refs
    return counts
