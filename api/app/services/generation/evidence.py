"""Generation v2 step 2: choose the facts and voice samples a draft may use (no LLM)."""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import generate_embeddings_batch
from app.models.fact import Fact
from app.models.proposal import Proposal
from app.schemas.fact import MAX_DETAIL, MAX_STATEMENT
from app.services.facts import search_facts
from app.services.generation.brief import JobBrief
from app.services.untrusted import neutralise

logger = logging.getLogger(__name__)

PER_NEED_CANDIDATES = 8
MIN_FACTS = 4
MAX_FACTS = 8
FILL_MIN_SCORE = 0.55
ANCHOR_MIN_SIMILARITY = 0.75
# Domain search: the facts closest to the brief's domain phrase ("fire safety inspections"), so a
# product in the client's own domain reaches the writer even when no single need names it. The whole
# post and the title are too diffuse: generic SaaS facts outrank the on-domain ones (round 4 probe).
DOMAIN_FACTS = 2
DOMAIN_MIN_SIMILARITY = 0.35  # on-domain facts scored 0.40-0.50 against a 2-5 word domain (round 4 probe)
VOICE_SAMPLE_LIMIT = 3
VOICE_AUTHORS = ("chris", "chris_edited_ai")
OUTCOME_BOOST = {"hired": 0.15, "interviewed": 0.10, "replied": 0.08, "viewed": 0.02}
# The embedding model takes 8,191 tokens per input. Its byte-level BPE never spends more than one
# token per UTF-8 byte, so clipping to 8,000 bytes keeps any script (CJK, emoji) under the limit.
EMBED_MAX_BYTES = 8_000
VOICE_UNAVAILABLE_WARNING = "Voice samples were unavailable, so the draft was written without them."


def _clip_for_embedding(text: str) -> str:
    return text.encode("utf-8")[:EMBED_MAX_BYTES].decode("utf-8", "ignore")


class EvidenceUnavailable(Exception):
    """Fact retrieval failed: generating anyway would silently produce an ungrounded letter."""


def rerank_score(similarity: float, strength: float, times_used: int, times_in_won: int) -> float:
    """0.55·similarity + 0.25·strength + 0.20·win_signal, win_signal Laplace-smoothed."""
    win_signal = (times_in_won + 1) / (times_used + 2)
    return 0.55 * similarity + 0.25 * strength + 0.20 * win_signal


@dataclass
class Evidence:
    facts: list[Fact] = field(default_factory=list)
    voice_samples: list[Proposal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def format_facts(facts: list[Fact]) -> str:
    """Render facts as a JSON array of {id, kind, statement, detail?}; ids are what the writer
    cites. JSON escapes newlines/quotes, so fact text cannot forge another entry, and statement
    and detail (which can hold client text) are neutralised."""
    if not facts:
        return "(no approved facts matched this job)"
    entries = []
    for fact in facts:
        entry = {"id": str(fact.id), "kind": fact.kind,
                 "statement": neutralise(fact.statement or "", MAX_STATEMENT)}
        if fact.detail:
            entry["detail"] = neutralise(fact.detail, MAX_DETAIL)
        entries.append(entry)
    return json.dumps(entries, ensure_ascii=False, indent=1)


def _select_facts(per_need: list[list[tuple[Fact, float]]]) -> list[Fact]:
    """Best unseen fact per need first, then fill by global score (4-8 total)."""
    scored = [
        sorted(
            (
                (fact, rerank_score(sim, fact.strength or 0.0, fact.times_used or 0, fact.times_in_won or 0))
                for fact, sim in candidates
            ),
            key=lambda pair: pair[1],
            reverse=True,
        )
        for candidates in per_need
    ]

    chosen: list[Fact] = []
    seen: set[str] = set()
    for ranked in scored:
        if len(chosen) >= MAX_FACTS:
            break
        for fact, _ in ranked:
            if str(fact.id) not in seen:
                chosen.append(fact)
                seen.add(str(fact.id))
                break

    pool = sorted((pair for ranked in scored for pair in ranked), key=lambda pair: pair[1], reverse=True)
    for fact, score in pool:
        if len(chosen) >= MAX_FACTS:
            break
        if str(fact.id) in seen:
            continue
        if len(chosen) >= MIN_FACTS and score < FILL_MIN_SCORE:
            break
        chosen.append(fact)
        seen.add(str(fact.id))
    return chosen


async def _find_voice_samples(
    db: AsyncSession,
    user_id: str,
    query_embedding: list[float],
    limit: int = VOICE_SAMPLE_LIMIT,
    exclude_ids: Optional[list[str]] = None,
) -> list[Proposal]:
    """Chris-written proposals for similar jobs, nudged toward ones that got traction.
    `exclude_ids` match either proposals.id or proposals.upwork_proposal_id."""
    distance = Proposal.job_needs_embedding.cosine_distance(query_embedding)
    stmt = (
        select(Proposal, (1 - distance).label("similarity"))
        .where(
            Proposal.user_id == user_id,
            Proposal.author.in_(VOICE_AUTHORS),
            Proposal.job_needs_embedding.isnot(None),
            func.length(func.trim(Proposal.cover_letter_text)) > 0,
        )
        .order_by(distance)
        .limit(limit * 4)
    )
    if exclude_ids:
        excluded = [str(i) for i in exclude_ids]
        stmt = stmt.where(
            Proposal.id.not_in(excluded),
            or_(Proposal.upwork_proposal_id.is_(None), Proposal.upwork_proposal_id.not_in(excluded)),
        )
    rows = (await db.execute(stmt)).all()
    ranked = sorted(
        rows,
        key=lambda row: row.similarity + OUTCOME_BOOST.get(row.Proposal.outcome or "", 0.0),
        reverse=True,
    )
    return [row.Proposal for row in ranked[:limit]]


async def select_evidence(
    db: AsyncSession,
    user_id: str,
    brief: JobBrief,
    anchors: Optional[dict],
    exclude_proposal_ids: Optional[list[str]] = None,
) -> Evidence:
    """Per-need fact retrieval + rerank, always-include floor, whole-job domain facts, and 2-3
    voice samples."""
    needs = [n for n in brief.needs if n.strip()]
    always = [a for a in ((anchors or {}).get("always_include") or []) if isinstance(a, str) and a.strip()]
    # Job<->job: same text shape Phase 1 (Task 1.8) and Phase 3 (Task 3.4) embed into
    # proposals.job_needs_embedding ("title\n\ndescription"); needs are the fallback.
    voice_query = _clip_for_embedding(
        "\n\n".join(t for t in (brief.title, brief.description) if t) or "\n".join(needs)
    )
    texts = [_clip_for_embedding(t) for t in needs + always]
    if not texts and not voice_query:
        return Evidence()

    vectors: list[list[float]] = []
    if texts:
        try:
            vectors = await generate_embeddings_batch(texts)
        except Exception as exc:
            logger.warning("Embeddings unavailable for evidence selection: %s", type(exc).__name__)
            raise EvidenceUnavailable("needs/anchors embedding failed") from exc

    need_vectors = vectors[: len(needs)]
    anchor_vectors = vectors[len(needs) : len(needs) + len(always)]

    per_need = [await search_facts(db, user_id, vec, limit=PER_NEED_CANDIDATES) for vec in need_vectors]
    facts = _select_facts(per_need)
    seen = {str(f.id) for f in facts}

    for vec in anchor_vectors:
        hits = await search_facts(db, user_id, vec, limit=1)
        if hits and hits[0][1] >= ANCHOR_MIN_SIMILARITY and str(hits[0][0].id) not in seen:
            facts.append(hits[0][0])
            seen.add(str(hits[0][0].id))

    # Embedded on its own: if the job-text embedding still fails it costs only the domain facts
    # and voice samples (with a warning), never the per-need facts.
    voice: list[Proposal] = []
    warnings: list[str] = []
    if voice_query:
        try:
            domain_text = _clip_for_embedding(brief.domain.strip())
            job_vectors = await generate_embeddings_batch([voice_query, domain_text] if domain_text else [voice_query])
            job_vector = job_vectors[0]
            domain_vector = job_vectors[1] if domain_text else None
        except Exception as exc:
            logger.warning("Voice-sample query embedding failed: %s", type(exc).__name__)
            warnings.append(VOICE_UNAVAILABLE_WARNING)
        else:
            domain = await search_facts(db, user_id, domain_vector, limit=DOMAIN_FACTS) if domain_vector else []
            for fact, similarity in domain:
                if similarity >= DOMAIN_MIN_SIMILARITY and str(fact.id) not in seen:
                    facts.append(fact)
                    seen.add(str(fact.id))
            voice = await _find_voice_samples(db, user_id, job_vector, exclude_ids=exclude_proposal_ids)
    return Evidence(facts=facts, voice_samples=voice, warnings=warnings)
