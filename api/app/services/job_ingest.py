"""Helpers for POST /api/v1/job-queue/ingest (jobs the extension gathers from Upwork search pages).

Identity: a job is its Upwork id (the "~0..." slug in the URL), falling back to the exact URL.
"""
import re
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Set, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.job_queue import JobQueueItem

UPWORK_JOB_SLUG = re.compile(r"~(0[0-9a-zA-Z]+)")

SOURCE = "extension_scan"
MAX_SCORED_PER_REQUEST = 25
DEFAULT_SCORE_THRESHOLD = 55.0
QUEUE_TTL_DAYS = 7
MAX_CHIPS = 6

# The chip vocabulary the job queue uses (agent/job_discovery.py SYSTEM_PROMPT).
CHIP_VOCABULARY = (
    "python", "fastapi", "react", "typescript", "sql", "postgresql", "azure", "aws", "ai", "llm",
    "saas", "mvp", "cto", "advisory", "fullstack", "data", "automation", "backend", "frontend",
)
_CHIP_ALIASES = {
    "postgres": "postgresql", "full stack": "fullstack", "full-stack": "fullstack",
    "artificial intelligence": "ai", "machine learning": "ai", "openai": "llm", "chatgpt": "llm",
    "gpt": "llm", "back end": "backend", "back-end": "backend", "front end": "frontend",
    "front-end": "frontend", "fractional cto": "cto", "ms sql": "sql", "mysql": "sql",
    "sql server": "sql",
}
_CHIP_TERMS = [(c, c) for c in CHIP_VOCABULARY] + list(_CHIP_ALIASES.items())


def upwork_job_slug(url: Optional[str]) -> Optional[str]:
    """The Upwork job id ("0123abc...", lowercased) in a job URL, or None."""
    match = UPWORK_JOB_SLUG.search(url or "")
    return match.group(1).lower() if match else None


def parse_posted_at(value: Optional[str]) -> Optional[datetime]:
    """ISO-8601 → aware datetime; None when missing or unreadable (the job is not rejected)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def known_job_keys(
    db: AsyncSession, user_id: str, urls: Iterable[str]
) -> Tuple[Set[str], Set[str]]:
    """(slugs, urls) of this user's job_queue items and jobs rows that match any of `urls`."""
    urls = list(dict.fromkeys(urls))
    slugs = {s for s in (upwork_job_slug(u) for u in urls) if s}

    def url_match(column):
        conds = [column.in_(urls)] if urls else []
        conds += [func.lower(column).contains(f"~{s}") for s in slugs]
        return or_(*conds)

    if not urls:
        return set(), set()
    found_urls: Set[str] = set()
    found_urls.update((await db.execute(
        select(JobQueueItem.upwork_url).where(
            JobQueueItem.user_id == user_id, url_match(JobQueueItem.upwork_url))
    )).scalars().all())
    job_conds = [url_match(Job.upwork_url)]
    if slugs:
        job_conds.append(func.lower(Job.upwork_job_id).in_(list(slugs) + [f"~{s}" for s in slugs]))
    found_slugs: Set[str] = set()
    for job_url, job_id in (await db.execute(
        select(Job.upwork_url, Job.upwork_job_id).where(Job.user_id == user_id, or_(*job_conds))
    )).all():
        found_urls.add(job_url)
        if job_id:
            found_slugs.add(job_id.lower().lstrip("~"))
    found_slugs.update(s for s in (upwork_job_slug(u) for u in found_urls) if s)
    return found_slugs, found_urls


def derive_chips(title: str, skills: Iterable[str]) -> List[str]:
    """Category chips from the title and skills, in vocabulary order, at most MAX_CHIPS."""
    text = " ".join([title or "", *(skills or [])]).lower()
    hits = {chip for term, chip in _CHIP_TERMS
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text)}
    return [c for c in CHIP_VOCABULARY if c in hits][:MAX_CHIPS]


def analysis_reasoning(ar) -> str:
    """One-line ai_reasoning from an AnalysisResult."""
    parts = [f"Score: {ar.match_score}."]
    if ar.reason:
        parts.append(ar.reason.strip().rstrip(".") + ".")
    if ar.strengths:
        parts.append(f"Strengths: {', '.join(ar.strengths[:2])}.")
    if ar.missing_skills:
        parts.append(f"Missing: {', '.join(ar.missing_skills[:3])}.")
    return " ".join(parts)
