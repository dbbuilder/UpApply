"""SearchOptimizer — Level 6 auto-query tuning from winning job patterns.

At Level 6 (Optimizing), this module:
  1. Reads winning jobs (hired / responded) from the job_queue
  2. Extracts common skill keywords and title patterns
  3. Compares against existing search_queries
  4. Suggests new queries or title tweaks the agent should try

This is a suggestion-only module — it never modifies search_queries directly.
Callers decide whether to write suggestions back.
"""
import logging
import re
from collections import Counter
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_queue import JobQueueItem
from app.models.search_query import SearchQuery

logger = logging.getLogger(__name__)

# Skills/keywords to always ignore when building frequency tables
STOP_SKILLS = {
    "english", "communication", "writing", "team player", "self-motivated",
    "fast learner", "detail-oriented", "problem solving",
}

# Common title words that are not meaningful for query generation
STOP_TITLE_WORDS = {
    "developer", "engineer", "specialist", "consultant", "expert", "looking",
    "need", "wanted", "needed", "required", "seeking", "hire", "freelancer",
    "for", "and", "or", "a", "an", "the", "with", "to", "of", "in", "on",
}


def _extract_keywords_from_title(title: str) -> List[str]:
    """Extract meaningful keyword tokens from a job title."""
    words = re.sub(r"[^a-zA-Z0-9\s\+\#]", " ", title).lower().split()
    return [w for w in words if len(w) > 2 and w not in STOP_TITLE_WORDS]


async def analyze_winning_patterns(
    user_id: str,
    db: AsyncSession,
    limit: int = 50,
) -> Dict:
    """Analyze winning and high-response jobs to find common patterns.

    Returns a dict with:
      - top_skills: [(skill, count), ...]
      - top_title_keywords: [(keyword, count), ...]
      - avg_score: float
      - sample_titles: [str, ...]
    """
    # Fetch responded/invited/hired jobs
    result = await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.user_id == user_id,
            JobQueueItem.client_response_type.in_(["responded", "invited"]),
        ).order_by(JobQueueItem.client_response_at.desc()).limit(limit)
    )
    winning_jobs = result.scalars().all()

    if not winning_jobs:
        logger.info("User %s: no winning jobs to analyze", user_id)
        return {}

    skill_counter: Counter = Counter()
    title_keyword_counter: Counter = Counter()
    scores = []

    for job in winning_jobs:
        # Skill frequency
        for skill in (job.skills or []):
            normalized = skill.strip().lower()
            if normalized and normalized not in STOP_SKILLS and len(normalized) > 2:
                skill_counter[normalized] += 1

        # Title keyword frequency
        for kw in _extract_keywords_from_title(job.title or ""):
            title_keyword_counter[kw] += 1

        if job.ai_score is not None:
            scores.append(job.ai_score)

    avg_score = sum(scores) / len(scores) if scores else None
    sample_titles = [j.title[:80] for j in winning_jobs[:5]]

    return {
        "winning_job_count": len(winning_jobs),
        "top_skills": skill_counter.most_common(10),
        "top_title_keywords": title_keyword_counter.most_common(10),
        "avg_score": round(avg_score, 1) if avg_score else None,
        "sample_titles": sample_titles,
    }


async def suggest_query_improvements(
    user_id: str,
    db: AsyncSession,
) -> List[Dict]:
    """Return a list of suggested search_query improvements.

    Each suggestion is a dict:
      {
        "type": "new_query" | "add_skill_filter" | "title_variation",
        "suggested_value": str,
        "reason": str,
        "confidence": float,  # 0.0–1.0
      }

    Suggestions are never automatically applied — the caller decides.
    """
    patterns = await analyze_winning_patterns(user_id, db)
    if not patterns:
        return []

    # Existing search queries
    existing_result = await db.execute(
        select(SearchQuery).where(
            SearchQuery.user_id == user_id,
            SearchQuery.active == True,
        )
    )
    existing_queries = existing_result.scalars().all()
    existing_terms = {q.query.lower().strip() for q in existing_queries}

    suggestions = []
    winning_count = patterns.get("winning_job_count", 0)

    # Suggest new queries based on top skill pairs not covered by existing queries
    top_skills = [skill for skill, _ in patterns.get("top_skills", [])[:6]]
    for i, skill in enumerate(top_skills):
        for existing_q in existing_queries:
            if skill.lower() in existing_q.query.lower():
                break
        else:
            # This winning skill isn't in any existing search query
            count = dict(patterns.get("top_skills", [])).get(skill, 0)
            confidence = min(1.0, count / max(winning_count, 1))
            suggestions.append({
                "type": "new_query",
                "suggested_value": skill,
                "reason": f"Appeared in {count}/{winning_count} winning jobs but not in any current search",
                "confidence": round(confidence, 2),
            })

    # Suggest title keyword variations for existing queries
    top_keywords = patterns.get("top_title_keywords", [])[:5]
    for kw, count in top_keywords:
        # Check if any existing query already targets this keyword
        already_targeted = any(kw in q.query.lower() for q in existing_queries)
        if not already_targeted and count >= 3:
            confidence = min(1.0, count / max(winning_count, 1))
            suggestions.append({
                "type": "title_variation",
                "suggested_value": kw,
                "reason": f"Common in winning job titles ({count} occurrences) but not searched",
                "confidence": round(confidence, 2),
            })

    # Sort by confidence descending, cap at 5 suggestions
    suggestions.sort(key=lambda s: s["confidence"], reverse=True)
    return suggestions[:5]
