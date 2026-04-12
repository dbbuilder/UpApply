"""Upwork RSS search adapter.

Fetches jobs from the Upwork RSS feed using a search query's url_params.

Upwork RSS URL format:
  https://www.upwork.com/ab/feed/jobs/rss?{url_params}

The url_params column from search_queries contains the raw query string,
e.g. "q=python+fastapi&contractor_tier=2,3&t=0,1".

Usage:
    from agent.rss_adapter import fetch_jobs_from_rss, RawJob
    jobs = await fetch_jobs_from_rss("q=python+fastapi&contractor_tier=2,3", limit=20)
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

RSS_BASE = "https://www.upwork.com/ab/feed/jobs/rss"
# Regex to extract the Upwork job UID from a URL like:
#   https://www.upwork.com/jobs/~01abc123def456
_UID_RE = re.compile(r'~([0-9a-f]+)', re.IGNORECASE)
# Strip HTML tags from descriptions
_HTML_TAG_RE = re.compile(r'<[^>]+>', re.DOTALL)
# Match budget figures like "$500", "$1,000 Fixed" or "$25/hr - $75/hr"
_BUDGET_RE = re.compile(r'\$[\d,]+(?:\.\d+)?(?:\s*/\s*hr)?')


@dataclass
class RawJob:
    """A job parsed from the Upwork RSS feed."""

    title: str
    description: str
    upwork_url: str
    upwork_uid: Optional[str]
    posted_date: Optional[datetime]
    budget_amount: Optional[str]
    budget_type: Optional[str]
    skills: list[str]


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    clean = _HTML_TAG_RE.sub(' ', text)
    return ' '.join(clean.split())


def _extract_uid(url: str) -> Optional[str]:
    """Extract the Upwork job UID from a job URL."""
    match = _UID_RE.search(url)
    return match.group(0) if match else None  # returns "~01abc..." with tilde


def _parse_budget(description: str) -> tuple[Optional[str], Optional[str]]:
    """Heuristically extract budget amount and type from description text."""
    text_lower = description.lower()
    budget_type = None
    if 'hourly' in text_lower or '/hr' in text_lower:
        budget_type = 'hourly'
    elif 'fixed' in text_lower or 'budget' in text_lower:
        budget_type = 'fixed'

    amounts = _BUDGET_RE.findall(description)
    budget_amount = amounts[0] if amounts else None
    if budget_amount and len(amounts) >= 2:
        # Range — show "low - high"
        budget_amount = f"{amounts[0]} - {amounts[-1]}"
    return budget_amount, budget_type


def _parse_skills(description: str) -> list[str]:
    """Extract skills list from description.

    Upwork RSS includes a line like:
      <b>Skills</b>: Python, FastAPI, PostgreSQL
    """
    skills: list[str] = []
    # Look for "Skills:" or "<b>Skills</b>:" pattern
    skill_match = re.search(
        r'(?:Skills\s*[:\-]|<b>Skills</b>\s*[:\-])\s*([^\n<]+)',
        description, re.IGNORECASE
    )
    if skill_match:
        raw = skill_match.group(1)
        skills = [s.strip() for s in raw.split(',') if s.strip()]
    return skills[:20]  # cap at 20


def _parse_item(item_el: ET.Element, ns: dict) -> Optional[RawJob]:
    """Parse a single <item> element from the RSS feed."""
    def _text(tag: str) -> str:
        el = item_el.find(tag, ns)
        return (el.text or '').strip() if el is not None else ''

    title = _text('title')
    link = _text('link')
    raw_description = _text('description')
    pub_date_str = _text('pubDate')

    if not title or not link:
        return None

    # Clean description — strip HTML before further processing
    skills = _parse_skills(raw_description)
    budget_amount, budget_type = _parse_budget(raw_description)
    description = _strip_html(raw_description)

    # Parse pub date
    posted_date: Optional[datetime] = None
    if pub_date_str:
        # RFC 2822 format: "Sat, 12 Apr 2026 06:00:00 +0000"
        from email.utils import parsedate_to_datetime
        try:
            posted_date = parsedate_to_datetime(pub_date_str)
        except Exception:
            logger.debug("Could not parse date: %s", pub_date_str)

    return RawJob(
        title=title,
        description=description[:2000],  # cap at 2000 chars for scoring
        upwork_url=link,
        upwork_uid=_extract_uid(link),
        posted_date=posted_date,
        budget_amount=budget_amount,
        budget_type=budget_type,
        skills=skills,
    )


async def fetch_jobs_from_rss(
    url_params: str,
    limit: int = 25,
    timeout: float = 15.0,
) -> list[RawJob]:
    """Fetch jobs from the Upwork RSS feed.

    Args:
        url_params: Raw query string from search_queries.url_params,
                    e.g. "q=python+fastapi&contractor_tier=2,3&t=0,1"
        limit:      Maximum number of jobs to return (Upwork RSS caps at 10-25).
        timeout:    HTTP timeout in seconds.

    Returns:
        List of RawJob dataclasses, sorted newest-first.
        Returns empty list on any network or parse error (logged at WARNING).
    """
    # Ensure the q= parameter is present; RSS requires it
    if not url_params:
        logger.warning("rss_adapter: empty url_params, skipping")
        return []

    # Build URL — Upwork RSS uses paging=0-N to limit results
    params = f"{url_params}&paging=0-{limit}"
    url = f"{RSS_BASE}?{params}"

    logger.info("rss_adapter: fetching %s", url)

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "UpApply/1.0 job-discovery-agent"},
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("rss_adapter: HTTP error for url_params=%r: %s", url_params, exc)
        return []

    # Parse XML
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        logger.warning("rss_adapter: XML parse error: %s", exc)
        return []

    # Namespace map (Upwork RSS may include content: namespace)
    ns: dict = {}

    channel = root.find('channel')
    if channel is None:
        logger.warning("rss_adapter: no <channel> in RSS response")
        return []

    jobs: list[RawJob] = []
    for item_el in channel.findall('item'):
        job = _parse_item(item_el, ns)
        if job:
            jobs.append(job)

    logger.info("rss_adapter: parsed %d jobs from url_params=%r", len(jobs), url_params[:60])
    return jobs[:limit]
