"""Search Lab service layer — coverage evaluation and query optimization.

Provides helper functions for the /search-queries/evaluate and /optimize
endpoints. Extracted from the router to keep business logic testable and
the router file focused on HTTP concerns.
"""
import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings
from app.models.user import UserProfile
from app.schemas.search_query import (
    QueryCoverage,
    SuggestedQuery,
    QueryExperimentResult,
    QueryVariant,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default URL params appended to all generated suggestions
_LAB_BASE_PARAMS = "contractor_tier=2,3&t=0,1"

_OPT_LOW_VOLUME = 5        # fewer jobs than this = low volume
_OPT_LOW_QUALITY = 0.30    # hit-rate below this = low quality


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

class TargetJob:
    """Lightweight job record used for coverage scoring."""

    def __init__(self, title: str, description: str = "") -> None:
        self.title = title
        self.description = description


def tokenize_query(query: str) -> list[str]:
    """Split query into meaningful tokens, strip noise words."""
    stop = {"a", "an", "the", "and", "or", "for", "in", "of", "to", "with", "is", "on", "at"}
    tokens = [w.lower().strip("\"'()") for w in query.split()]
    return [t for t in tokens if t and t not in stop and len(t) > 1]


def job_matches_query(title: str, description: str, tokens: list[str]) -> bool:
    """Return True if any token appears in the job title or description."""
    text = (title + " " + (description or "")).lower()
    return any(t in text for t in tokens)


# ---------------------------------------------------------------------------
# AI helpers
# ---------------------------------------------------------------------------

async def generate_lab_suggestions(
    gap_titles: list[str],
    all_target_titles: list[str],
    existing_queries: list[str],
    profile: Optional[UserProfile],
) -> list[SuggestedQuery]:
    """Call GPT to generate new Upwork search queries covering the gap jobs."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    gap_block = "\n".join(f"  • {t}" for t in gap_titles)
    all_block = "\n".join(f"  • {t}" for t in all_target_titles[:30])
    existing_block = "\n".join(f"  • {q}" for q in existing_queries[:30])

    skills_str = ", ".join(
        s["name"] for s in (profile.skills or []) if s.get("level") in ("expert", "intermediate")
    ) if profile else "not specified"
    rate = getattr(profile, "hourly_rate", None) if profile else None
    rate_str = f"${rate}/hr" if rate else "not set"

    prompt = f"""You are an expert Upwork search strategist for a senior freelancer.

FREELANCER PROFILE:
- Skills: {skills_str}
- Hourly rate: {rate_str}
- Title: {getattr(profile, 'professional_title', 'Senior Developer') if profile else 'Senior Developer'}

ALL WINNING JOB TITLES (contracts won + proposals that got responses):
{all_block}

UNCOVERED GAP JOBS (winning jobs that no current search would find):
{gap_block}

EXISTING SEARCH QUERIES (do not duplicate):
{existing_block}

UPWORK ADVANCED SEARCH URL PARAMS REFERENCE:
- q=KEYWORDS           — "All of these words" (AND logic) — main search term
- t=0,1                — job type: 0=hourly, 1=fixed-price (use both unless job-type-specific)
- contractor_tier=2,3  — Intermediate + Expert only (always include)
- hourly_rate=MIN-MAX  — hourly rate range (e.g. hourly_rate=100- for $100+/hr min)
- amount=MIN-MAX       — fixed price budget (e.g. amount=1000- for $1k+ min)
- skills=SKILL         — filter by specific Upwork skill tag

TASK: Generate 5 targeted search queries that would find the uncovered gap jobs.

For each query, output EXACTLY this JSON format (one object per line, no array wrapper):
{{"query": "keyword phrase here", "url_params": "contractor_tier=2,3&t=0,1&hourly_rate=100-", "reasoning": "one sentence why this covers the gap", "gap_jobs_targeted": ["Gap Job Title 1", "Gap Job Title 2"]}}

Rules:
- query: 2-5 words, what a CLIENT would search for (not just skill names)
- url_params: always include contractor_tier=2,3; add appropriate rate filters based on job type
- For CTO/advisory/strategy work: no strict rate filter (fixed-price projects vary widely)
- For technical implementation: hourly_rate=100- is appropriate
- reasoning: be specific about which gap jobs this captures and why
- gap_jobs_targeted: list the exact gap job titles this query would likely surface
- Think about the SEMANTIC match: "AI automation" might cover "Machine Learning Pipeline" jobs
- Include role-framing queries ("fractional CTO", "technical advisor") for strategic gap jobs"""

    response = await client.chat.completions.create(
        model=settings.default_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=800,
    )

    raw = response.choices[0].message.content or ""
    suggestions: list[SuggestedQuery] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            if obj.get("query") and obj.get("url_params"):
                suggestions.append(SuggestedQuery(
                    query=obj["query"],
                    url_params=obj.get("url_params", _LAB_BASE_PARAMS),
                    reasoning=obj.get("reasoning", ""),
                    gap_jobs_targeted=obj.get("gap_jobs_targeted", []),
                ))
        except Exception:
            continue

    return suggestions[:6]  # cap at 6 suggestions


async def generate_optimize_variants(
    weak_experiments: list[QueryExperimentResult],
    profile: Optional[UserProfile],
) -> dict[str, list[QueryVariant]]:
    """Call GPT to generate improved variants for underperforming queries.

    Returns a dict mapping query_id → list of QueryVariant objects.
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    skills_str = ", ".join(
        s["name"] for s in (profile.skills or []) if s.get("level") in ("expert", "intermediate")
    ) if profile else "not specified"
    title_str = getattr(profile, "professional_title", "Senior Developer") if profile else "Senior Developer"

    weak_block = ""
    for exp in weak_experiments:
        hit_rate = exp.high_score_count / max(exp.jobs_returned, 1) * 100
        low_vol = exp.jobs_returned < _OPT_LOW_VOLUME
        low_qual = hit_rate < _OPT_LOW_QUALITY * 100
        if low_vol and low_qual:
            problem = "BOTH — too narrow AND low quality"
        elif low_vol:
            problem = "TOO NARROW (found too few jobs)"
        else:
            problem = "LOW QUALITY (too many irrelevant results)"
        good_ex = ", ".join(exp.sample_good_titles[:2]) or "none"
        bad_ex = ", ".join(exp.sample_bad_titles[:2]) or "none"
        weak_block += (
            f'Query: "{exp.query}" | url_params: {exp.url_params or "none"}\n'
            f"  Problem: {problem} — {exp.jobs_returned} jobs found, "
            f"{exp.high_score_count} high-score ({hit_rate:.0f}% hit rate)\n"
            f"  Good matches: {good_ex}\n"
            f"  Irrelevant matches: {bad_ex}\n"
            f"  query_id: {exp.query_id}\n\n"
        )

    prompt = f"""You are an expert Upwork search optimizer for a senior freelancer.

FREELANCER TITLE: {title_str}
FREELANCER SKILLS: {skills_str}

UNDERPERFORMING SEARCH QUERIES:
{weak_block}
UPWORK SEARCH URL PARAMS:
- q=KEYWORDS — all-words AND search (main term)
- t=0,1 — hourly + fixed-price (use both unless job-type-specific)
- contractor_tier=2,3 — Intermediate + Expert only (always include)
- hourly_rate=MIN- — e.g. hourly_rate=75- for $75+/hr minimum
- amount=MIN- — fixed-price budget minimum

For each query above, generate 2-3 IMPROVED VARIANTS.

RULES:
- TOO NARROW: make the query BROADER (fewer required words, more general terms, or drop modifiers)
- LOW QUALITY: make it MORE SPECIFIC (add domain context, role framing, niche terms that filter noise)
- BOTH: try completely different angle (different client phrasing, different role framing)
- ALWAYS prefer INCLUSIVE queries — optimise for finding MORE good jobs, not perfect precision
- change_type must be one of: "broader", "narrower", "reframe"

Output EXACTLY this JSON format, one object per line, nothing else:
{{"query_id": "the_query_id", "query": "new keyword phrase", "url_params": "contractor_tier=2,3&t=0,1", "reasoning": "one sentence why this improves recall", "change_type": "broader"}}"""

    response = await client.chat.completions.create(
        model=settings.default_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=900,
    )

    raw = response.choices[0].message.content or ""
    result: dict[str, list[QueryVariant]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            qid = obj.get("query_id", "")
            if qid and obj.get("query") and obj.get("url_params"):
                if qid not in result:
                    result[qid] = []
                if len(result[qid]) < 3:
                    result[qid].append(QueryVariant(
                        query=obj["query"],
                        url_params=obj["url_params"],
                        reasoning=obj.get("reasoning", ""),
                        change_type=obj.get("change_type", "broader"),
                    ))
        except Exception:
            continue

    return result
