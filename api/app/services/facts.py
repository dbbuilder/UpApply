"""Fact store: embedding, dedupe/merge, auto-approve, semantic search, outcome crediting.

Nothing here commits — callers own the transaction (routers commit; get_db commits too).
"""
import asyncio
import hashlib
import logging
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import generate_embedding
from app.models.fact import Fact, FactIngestLog
from app.schemas.fact import FactCandidate, FactIngestItem
from app.services.fact_extraction import extract_facts

logger = logging.getLogger(__name__)

DEDUPE_THRESHOLD = 0.92
# Linear (separators required between digit runs, so no overlapping quantifiers).
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers_conflict(a: str, b: str) -> bool:
    """True when both texts state numbers and the sets differ ("160 servers" vs "120 servers"):
    embeddings rank such pairs as near-duplicates, but merging would silently drop one value."""
    na, nb = set(_NUMBER.findall(a or "")), set(_NUMBER.findall(b or ""))
    return bool(na and nb and na != nb)
# Records written by clients / Upwork about the user (contracts, feedback). Never auto-approved,
# not even by matching an approved fact (§1.7): they only ever add provenance.
CLIENT_SOURCE_TYPES = frozenset({"client_feedback", "upwork_contract"})


def _is_client_sourced(cand: FactCandidate) -> bool:
    return cand.source_type in CLIENT_SOURCE_TYPES or cand.kind == "client_quote"
MAX_CONCURRENT_EXTRACTIONS = 5  # parallel Haiku calls per request
MAX_EXTRACTION_ATTEMPTS = 3     # an item that fails this often is given up on
MAX_ITEMS_PER_RUN = 25          # /from-memories and /from-contracts batch size


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


async def _exact_nearest(
    db: AsyncSession, embedding: List[float], limit: int, *filters
) -> List[Tuple[Fact, float]]:
    """Exact cosine ranking over only the rows matching `filters`.

    The filter runs first in a MATERIALIZED CTE, so the HNSW index can never return a global
    top-K (other users' / other statuses' rows) that the WHERE then empties. Per-user fact
    counts are small (hundreds), so the exact scan is cheap and pgvector-version independent."""
    scoped = (
        select(Fact.id.label("id"), Fact.embedding.label("embedding"))
        .where(Fact.embedding.is_not(None), *filters)
        .cte("scoped_facts")
        .prefix_with("MATERIALIZED")
    )
    distance = scoped.c.embedding.cosine_distance(embedding)
    rows = (await db.execute(
        select(Fact, (1 - distance).label("similarity"))
        .join(scoped, scoped.c.id == Fact.id)
        .order_by(distance)
        .limit(limit)
    )).all()
    return [(row[0], float(row[1])) for row in rows]


async def _nearest(
    db: AsyncSession, user_id: str, embedding: List[float]
) -> Optional[Tuple[Fact, float]]:
    rows = await _exact_nearest(db, embedding, 1, Fact.user_id == user_id)
    return rows[0] if rows else None


async def upsert_candidate_outcome(
    db: AsyncSession,
    user_id: str,
    cand: FactCandidate,
    auto_approve: bool = False,
) -> Tuple[Fact, str]:
    """Insert or merge one candidate; returns (fact, 'created' | 'merged' | 'auto_approved')."""
    client_sourced = _is_client_sourced(cand)
    if client_sourced:
        auto_approve = False
    embedding = await generate_embedding(fact_embedding_text(cand.statement, cand.detail))
    nearest = await _nearest(db, user_id, embedding)
    if nearest and _numbers_conflict(cand.statement, nearest[0].statement):
        nearest = None  # conflicting figures: keep both, the new one goes to review

    if nearest and nearest[1] >= DEDUPE_THRESHOLD:
        fact = nearest[0]
        fact.sources = [*(fact.sources or []), _source_entry(cand)]
        if client_sourced:
            # Client/contract records: provenance only; wording, ranking and status untouched.
            await db.flush()
            return fact, "merged"
        if fact.status == "approved" and not auto_approve:
            # Untrusted candidate matching an approved fact: provenance only. Ranking fields
            # (tags, strength) change only via user PATCH, manual create or a trusted source.
            await db.flush()
            return fact, "auto_approved"
        if auto_approve and fact.status == "candidate":
            # A trusted source approving an unreviewed candidate: the trusted wording AND ranking
            # fields win, so nothing an untrusted or client-sourced candidate added (inflated
            # claim, tags, strength, origin) is carried into the approved fact (§1.7).
            fact.kind = cand.kind
            fact.statement = cand.statement
            fact.detail = cand.detail
            fact.embedding = embedding
            fact.skills = list(cand.skills)
            fact.industries = list(cand.industries)
            fact.job_types = list(cand.job_types)
            fact.strength = cand.strength
            fact.source_type = cand.source_type
            fact.source_ref = cand.source_ref
            fact.status = "approved"
        else:
            fact.skills = _union(fact.skills, cand.skills)
            fact.industries = _union(fact.industries, cand.industries)
            fact.job_types = _union(fact.job_types, list(cand.job_types))
            if fact.status != "approved" and cand.strength > fact.strength:
                # Unreviewed fact: keep the strongest wording. Approved wording is never touched.
                fact.statement = cand.statement
                fact.detail = cand.detail
                fact.embedding = embedding
            fact.strength = max(fact.strength, cand.strength)
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
    return await _exact_nearest(
        db, query_embedding, limit, Fact.user_id == user_id, Fact.status == status
    )


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


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def _ingest_log(
    db: AsyncSession, user_id: str, source_type: str, refs: List[str]
) -> Dict[str, FactIngestLog]:
    if not refs:
        return {}
    rows = (await db.execute(
        select(FactIngestLog).where(
            FactIngestLog.user_id == user_id,
            FactIngestLog.source_type == source_type,
            FactIngestLog.source_ref.in_(refs),
        )
    )).scalars().all()
    return {r.source_ref: r for r in rows}


def _is_settled(row: Optional[FactIngestLog], text: str) -> bool:
    """Same text already extracted, or given up on after repeated failures."""
    return bool(
        row
        and row.content_hash == _content_hash(text)
        and (row.status == "done" or row.attempts >= MAX_EXTRACTION_ATTEMPTS)
    )


async def ingest_items(
    db: AsyncSession,
    user_id: str,
    source_type: str,
    items: List[FactIngestItem],
    auto_approve: bool = False,
    max_items: Optional[int] = None,
) -> dict:
    """Extract candidates from each item and upsert them.

    Every item with a source_ref is recorded in fact_ingest_log (including zero-fact results),
    so re-runs only pay for new or changed text. Failures are retried up to
    MAX_EXTRACTION_ATTEMPTS. At most `max_items` items are extracted per call
    (`remaining` counts the rest) and at most MAX_CONCURRENT_EXTRACTIONS run at once."""
    counts = {"created": 0, "merged": 0, "auto_approved": 0, "skipped": 0, "failed": 0}
    log = await _ingest_log(db, user_id, source_type, [i.source_ref for i in items if i.source_ref])

    pending: List[FactIngestItem] = []
    seen: set = set()
    for item in items:
        if item.source_ref and (item.source_ref in seen or _is_settled(log.get(item.source_ref), item.text)):
            counts["skipped"] += 1
            continue
        if item.source_ref:
            seen.add(item.source_ref)
        pending.append(item)
    if max_items is not None:
        pending, rest = pending[:max_items], pending[max_items:]
    else:
        rest = []

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)

    async def _extract(i: FactIngestItem):
        async with semaphore:
            return await extract_facts(i.text, source_type, i.source_ref, i.context)

    results = await asyncio.gather(*(_extract(i) for i in pending), return_exceptions=True)

    retry_refs: List[str] = []
    failed_refs: List[Optional[str]] = []
    for item, result in zip(pending, results):
        failed = isinstance(result, BaseException)
        if failed:
            logger.warning("Fact extraction failed for %s/%s: %s", source_type, item.source_ref, result)
            counts["failed"] += 1
            failed_refs.append(item.source_ref)
        else:
            for cand in result:
                _, outcome = await upsert_candidate_outcome(db, user_id, cand, auto_approve)
                counts[outcome] += 1
        if not item.source_ref:
            continue
        digest = _content_hash(item.text)
        row = log.get(item.source_ref)
        if row is None:
            row = FactIngestLog(
                user_id=user_id, source_type=source_type, source_ref=item.source_ref,
                content_hash=digest, status="done", attempts=0,
            )
            db.add(row)
        elif row.content_hash != digest:
            row.content_hash = digest
            row.attempts = 0
        row.status = "failed" if failed else "done"
        row.attempts = row.attempts + 1 if failed else 0
        if failed and row.attempts < MAX_EXTRACTION_ATTEMPTS:
            retry_refs.append(item.source_ref)
    await db.flush()

    counts["remaining"] = len(rest)
    # Not FactIngestResult fields. failed_refs: every ref whose extraction raised this call.
    # retry_refs: the subset still under MAX_EXTRACTION_ATTEMPTS, which /from-proposals leaves
    # unmarked so they are retried; the rest are given up on.
    counts["failed_refs"] = failed_refs
    counts["retry_refs"] = retry_refs
    return counts
