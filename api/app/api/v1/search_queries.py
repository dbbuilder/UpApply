"""Search query management endpoints.

Implements the intelligent job search library: saved queries with cumulative
performance statistics, profile-seeded bootstrapping, and AI-generated variants.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserProfile
from app.models.job import Job
from app.models.search_query import SearchQuery
from app.schemas.search_query import (
    SearchQueryCreate,
    SearchQueryResponse,
    RunRecordRequest,
    BulkImportSearchQueriesRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HIGH_SCORE_THRESHOLD = 70.0


def _normalize_query(q: str) -> str:
    """Lowercase and collapse whitespace for deduplication."""
    return " ".join(q.lower().split())


def _to_response(sq: SearchQuery) -> SearchQueryResponse:
    return SearchQueryResponse(
        id=sq.id,
        query=sq.query,
        url_params=sq.url_params,
        source=sq.source,
        active=sq.active,
        run_count=sq.run_count,
        last_run_at=sq.last_run_at,
        total_jobs_found=sq.total_jobs_found,
        avg_match_score=sq.avg_match_score,
        high_score_count=sq.high_score_count,
        performance_score=sq.performance_score,
        is_stale=sq.is_stale,
        is_low_performer=sq.is_low_performer,
        created_at=sq.created_at,
    )


async def _get_profile(db: AsyncSession, user_id: str) -> Optional[UserProfile]:
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _existing_normalized_queries(db: AsyncSession, user_id: str) -> set[str]:
    """Return the set of normalised query strings already in the library."""
    result = await db.execute(
        select(SearchQuery.query).where(
            SearchQuery.user_id == user_id, SearchQuery.active.is_(True)
        )
    )
    return {_normalize_query(row[0]) for row in result.all()}


async def _insert_unique(
    db: AsyncSession,
    user_id: str,
    query: str,
    source: str,
    existing: set[str],
    url_params: Optional[str] = None,
    parent_query_id: Optional[str] = None,
) -> Optional[SearchQuery]:
    """Insert a query only if its normalised form is not already present."""
    norm = _normalize_query(query)
    if norm in existing:
        return None
    existing.add(norm)
    sq = SearchQuery(
        id=str(uuid4()),
        user_id=user_id,
        query=query.strip(),
        url_params=url_params,
        source=source,
        parent_query_id=parent_query_id,
    )
    db.add(sq)
    return sq


# ---------------------------------------------------------------------------
# Seed query generation (rule-based, no AI)
# ---------------------------------------------------------------------------

# Premium URL filter preset for intermediate/expert, low-competition jobs
PREMIUM_PARAMS = "contractor_tier=2,3&proposals=0-4"

# Domain-aware seed templates keyed by skill name fragments
_DOMAIN_EXTRAS: list[tuple[str, list[str]]] = [
    # (skill fragment, extra queries)
    ("sql", ["SQL database performance optimization", "database migration expert",
             "data engineering consultant"]),
    ("postgresql", ["PostgreSQL performance tuning", "pgvector developer",
                    "PostgreSQL database architect"]),
    ("azure", ["Azure cost optimization", "cloud cost control Azure",
               "Azure infrastructure consultant"]),
    ("aws", ["AWS cost optimization", "cloud architecture AWS",
             "AWS FinOps consultant"]),
    ("gcp", ["GCP cloud architecture", "Google Cloud cost optimization"]),
    ("python", ["Python backend developer", "Python API developer",
                "FastAPI developer"]),
    ("fastapi", ["FastAPI REST API developer", "Python FastAPI backend"]),
    ("react", ["React TypeScript developer", "React frontend consultant"]),
    ("openai", ["OpenAI API developer", "LLM integration developer",
                "AI chatbot developer"]),
    ("langchain", ["LangChain developer", "RAG system developer",
                   "AI agent developer"]),
    ("cto", ["fractional CTO", "technical co-founder", "startup technical advisor",
             "CTO as a service"]),
    ("ai", ["AI automation engineer", "AI consulting", "AI workflow automation",
            "n8n AI automation", "Make.com advanced automation"]),
    ("security", ["compliance audit technical", "SOC2 implementation consultant",
                  "zero trust security implementation"]),
    ("compliance", ["SOC2 readiness consultant", "compliance infrastructure",
                    "security compliance engineer"]),
    ("saas", ["SaaS MVP developer", "SaaS startup technical advisor",
              "broken AI code fix"]),
    ("mvp", ["MVP rescue developer", "vibe coding fix", "AI generated code fix",
             "legacy code modernization"]),
]


def _generate_seed_queries(profile: UserProfile) -> list[dict]:
    """Generate rule-based seed queries from the user's profile.

    Returns a list of dicts: {query, url_params, source}.
    """
    seeds: list[dict] = []
    seen: set[str] = set()

    def add(query: str, url_params: Optional[str] = PREMIUM_PARAMS) -> None:
        norm = _normalize_query(query)
        if norm not in seen:
            seen.add(norm)
            seeds.append({"query": query.strip(), "url_params": url_params, "source": "seeded"})

    skills: list = profile.skills or []
    expert_skills = [s["name"] for s in skills if s.get("level") == "expert"]
    good_skills = [s["name"] for s in skills
                   if s.get("level") in ("expert", "intermediate")]

    # 1. Each expert/intermediate skill alone and as "X developer" / "X consultant"
    for s in good_skills[:8]:
        add(s)
        add(f"{s} developer")
        add(f"{s} consultant")

    # 2. Top skill pairs
    for i, s1 in enumerate(expert_skills[:4]):
        for s2 in expert_skills[i + 1:4]:
            add(f"{s1} {s2}")
            add(f"{s1} {s2} developer")

    # 3. Professional title
    if profile.professional_title:
        add(profile.professional_title)

    # 4. Preferred project types
    for pt in (profile.preferred_project_types or [])[:5]:
        add(pt)

    # 5. Domain-aware extras based on skill names
    skill_names_lower = {s["name"].lower() for s in skills}
    for fragment, extras in _DOMAIN_EXTRAS:
        if any(fragment in sn for sn in skill_names_lower):
            for q in extras:
                add(q)

    # 6. Skills to highlight
    for skill_name in (profile.skills_to_highlight or [])[:4]:
        add(f"{skill_name} expert")
        add(f"{skill_name} consultant")

    return seeds


# ---------------------------------------------------------------------------
# AI query generation
# ---------------------------------------------------------------------------

async def _generate_ai_queries(
    profile: UserProfile,
    top_queries: list[SearchQuery],
    top_jobs: list[Job],
    existing: set[str],
) -> list[str]:
    """Call GPT to generate new query variants.  Returns raw query strings."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    expert_skills = ", ".join(
        s["name"] for s in (profile.skills or []) if s.get("level") == "expert"
    ) or "not specified"
    preferred = ", ".join(profile.preferred_project_types or []) or "not specified"

    top_q_block = "\n".join(
        f'  "{sq.query}" → avg_score: {sq.avg_match_score or 0:.0f}, '
        f'jobs: {sq.total_jobs_found}, high_score: {sq.high_score_count}'
        for sq in top_queries
    ) or "  (no runs yet)"

    top_titles_block = "\n".join(
        f"  {job.title}" for job in top_jobs[:20]
    ) or "  (no high-scoring jobs yet)"

    # Aggregate skill frequency from top jobs
    skill_freq: dict[str, int] = {}
    for job in top_jobs:
        for skill in (job.skills_required or []):
            skill_freq[skill] = skill_freq.get(skill, 0) + 1
    top_skills_block = "\n".join(
        f"  {skill}: {count}"
        for skill, count in sorted(skill_freq.items(), key=lambda x: -x[1])[:15]
    ) or "  (none yet)"

    existing_block = "\n".join(f"  {q}" for q in sorted(existing)[:50])

    prompt = f"""You are a Upwork search strategist for a senior freelancer.

PROFILE:
- Title: {profile.professional_title or 'not set'}
- Expert skills: {expert_skills}
- Goals: {profile.career_goals or 'not set'}
- Preferred work: {preferred}

TOP PERFORMING QUERIES (produced high-scoring job matches):
{top_q_block}

HIGH-SCORING JOB TITLES FOUND:
{top_titles_block}

SKILLS THOSE JOBS REQUIRED (by frequency):
{top_skills_block}

EXISTING QUERIES (do not repeat these):
{existing_block}

Generate exactly 12 new Upwork search queries.

RULES:
- Output ONLY the q= parameter value (plain text, 2-5 words each)
- Think about what a CLIENT would type when looking for this freelancer
- Mix: exact skill combos, role+domain terms, problem-type queries, niche terms
- Avoid single generic words like "developer" or "engineer" alone
- Use Boolean operators where useful: "fractional CTO" OR "technical advisor"
- One query per line, nothing else — no numbering, no quotes around the line
"""

    response = await client.chat.completions.create(
        model=settings.default_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=400,
    )
    raw = response.choices[0].message.content or ""
    lines = [line.strip().strip('"').strip("'") for line in raw.splitlines()]
    return [line for line in lines if line and 2 <= len(line.split()) <= 10]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=List[SearchQueryResponse])
async def list_search_queries(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all saved search queries, sorted by performance score descending."""
    stmt = select(SearchQuery).where(SearchQuery.user_id == current_user.id)
    if not include_inactive:
        stmt = stmt.where(SearchQuery.active.is_(True))
    result = await db.execute(stmt)
    queries = result.scalars().all()
    # Sort in Python because performance_score is a computed property
    queries = sorted(queries, key=lambda q: q.performance_score, reverse=True)
    return [_to_response(sq) for sq in queries]


@router.post("", response_model=SearchQueryResponse, status_code=status.HTTP_201_CREATED)
async def create_search_query(
    data: SearchQueryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new search query (deduplicated by normalised query string)."""
    existing = await _existing_normalized_queries(db, current_user.id)
    sq = await _insert_unique(
        db, current_user.id, data.query, data.source, existing, data.url_params
    )
    if sq is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A search query with this text already exists in your library.",
        )
    await db.flush()
    await db.refresh(sq)
    return _to_response(sq)


@router.delete("/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search_query(
    query_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a search query (sets active=False)."""
    result = await db.execute(
        select(SearchQuery).where(
            SearchQuery.id == query_id,
            SearchQuery.user_id == current_user.id,
        )
    )
    sq = result.scalar_one_or_none()
    if sq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found.")
    sq.active = False


@router.post("/seed", response_model=List[SearchQueryResponse])
async def seed_search_queries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate seed queries from the user's profile (idempotent, rule-based).

    Safe to call multiple times — existing queries are never duplicated.
    Returns only the *newly created* queries.
    """
    profile = await _get_profile(db, current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete your profile before seeding search queries.",
        )

    seeds = _generate_seed_queries(profile)
    existing = await _existing_normalized_queries(db, current_user.id)
    created: list[SearchQuery] = []
    for seed in seeds:
        sq = await _insert_unique(
            db,
            current_user.id,
            seed["query"],
            seed["source"],
            existing,
            seed.get("url_params"),
        )
        if sq:
            created.append(sq)

    await db.flush()
    for sq in created:
        await db.refresh(sq)
    logger.info("Seeded %d new queries for user %s", len(created), current_user.id)
    return [_to_response(sq) for sq in created]


@router.post("/generate", response_model=List[SearchQueryResponse])
async def generate_search_queries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI-generate new query variants based on profile + high-performing history.

    Calls GPT with top-performing queries and high-scoring job titles to produce
    12 novel query strings that are deduplicated before insertion.
    """
    profile = await _get_profile(db, current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete your profile before generating queries.",
        )

    # Fetch top 5 performing queries (min 1 run)
    result = await db.execute(
        select(SearchQuery).where(
            SearchQuery.user_id == current_user.id,
            SearchQuery.active.is_(True),
            SearchQuery.run_count >= 1,
        )
    )
    all_qs = sorted(result.scalars().all(), key=lambda q: q.performance_score, reverse=True)
    top_queries = all_qs[:5]

    # Fetch top 20 high-scoring jobs from last 30 days
    thirty_days_ago = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    from datetime import timedelta
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(
        select(Job)
        .where(
            Job.user_id == current_user.id,
            Job.match_score >= HIGH_SCORE_THRESHOLD,
            Job.created_at >= thirty_days_ago,
        )
        .order_by(Job.match_score.desc())
        .limit(20)
    )
    top_jobs = result.scalars().all()

    existing = await _existing_normalized_queries(db, current_user.id)
    raw_queries = await _generate_ai_queries(profile, top_queries, top_jobs, existing)

    created: list[SearchQuery] = []
    for q in raw_queries:
        sq = await _insert_unique(
            db, current_user.id, q, "ai_generated", existing, PREMIUM_PARAMS
        )
        if sq:
            created.append(sq)

    await db.flush()
    for sq in created:
        await db.refresh(sq)
    logger.info("AI generated %d new queries for user %s", len(created), current_user.id)
    return [_to_response(sq) for sq in created]


@router.post("/{query_id}/record-run", response_model=SearchQueryResponse)
async def record_query_run(
    query_id: str,
    record: RunRecordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update cumulative stats after running a search query.

    Uses a weighted rolling average to accumulate avg_match_score across runs.
    """
    result = await db.execute(
        select(SearchQuery).where(
            SearchQuery.id == query_id,
            SearchQuery.user_id == current_user.id,
        )
    )
    sq = result.scalar_one_or_none()
    if sq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found.")

    prev_total = sq.total_jobs_found
    new_total = prev_total + record.jobs_found

    if new_total > 0:
        prev_avg = sq.avg_match_score or 0.0
        # Weighted rolling average: preserve history proportionally
        sq.avg_match_score = round(
            (prev_avg * prev_total + record.avg_score * record.jobs_found) / new_total,
            2,
        )

    sq.total_jobs_found = new_total
    sq.high_score_count += record.high_score_count
    sq.run_count += 1
    sq.last_run_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(sq)
    return _to_response(sq)


@router.post("/bulk-import", response_model=List[SearchQueryResponse])
async def bulk_import_search_queries(
    request: BulkImportSearchQueriesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-import search queries (e.g. from Upwork's saved searches UI).

    Deduplicates against existing library. Returns only newly created queries.
    """
    existing = await _existing_normalized_queries(db, current_user.id)
    created: list[SearchQuery] = []
    for item in request.queries:
        q = item.get("query", "").strip()
        if not q:
            continue
        sq = await _insert_unique(
            db,
            current_user.id,
            q,
            item.get("source", "imported"),
            existing,
            item.get("url_params"),
        )
        if sq:
            created.append(sq)

    await db.flush()
    for sq in created:
        await db.refresh(sq)
    return [_to_response(sq) for sq in created]
