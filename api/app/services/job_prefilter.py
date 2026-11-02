"""Cheap pre-filter run before a job is scored (no LLM): the rules behind the pre_filter:* codes.

Used by POST /api/v1/job-queue/ingest (jobs the extension gathers) and by the retired
agent/job_discovery.py. pre_filter() returns the raw skip string ("blocked_country (India)",
"too_old (9d)") that app.services.skip_reasons.normalise_pre_filter() turns into a canonical
code, or None when the job should be scored.

The fixed-price and hourly floors are the user's profile minimum_budget / minimum_hourly_rate
when set, else FIXED_BUDGET_MIN / HOURLY_MIN_TOP_RATE.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

MAX_JOB_AGE_DAYS = 7  # skip jobs older than this

# Budget floors used when the profile sets none
FIXED_BUDGET_MIN = 500.0
# Placeholder values many clients use when they don't know the budget yet
FIXED_BUDGET_PLACEHOLDERS = {5.0, 100.0}
HOURLY_MIN_TOP_RATE = 60.0  # top-end of range must be at least this

# Client geography blocks — skip jobs from these countries (only when the country is known)
BLOCKED_COUNTRIES: frozenset[str] = frozenset({
    # Indian subcontinent
    "india", "pakistan",
    # Middle East
    "saudi arabia", "uae", "united arab emirates", "qatar", "kuwait",
    "bahrain", "oman", "jordan", "lebanon", "iraq", "iran", "yemen",
    "syria", "israel", "palestine", "turkey",
    # North Africa
    "egypt", "algeria", "morocco", "tunisia", "libya", "sudan", "south sudan",
    # Sub-Saharan Africa
    "nigeria", "kenya", "ghana", "ethiopia", "tanzania", "south africa",
    "uganda", "cameroon", "senegal", "zimbabwe", "somalia", "mozambique",
    "madagascar", "ivory coast", "côte d'ivoire", "mali", "burkina faso",
    "niger", "chad", "angola", "democratic republic of congo", "congo",
    "rwanda", "burundi", "zambia", "malawi", "botswana", "namibia",
    "lesotho", "eswatini", "mauritius", "cape verde", "seychelles",
    "djibouti", "eritrea",
})
# Whole-word match, so "Romania" is not caught by "oman" (nor "Indiana" by "india")
_BLOCKED_COUNTRY_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(c) for c in sorted(BLOCKED_COUNTRIES, key=len, reverse=True)) + r")\b"
)

# Extracts ALL dollar figures from a budget string
_BUDGET_VALUE_RE = re.compile(r'\$\s*([\d,]+(?:\.\d+)?)')

# Upwork's relative "posted" text: "3 days ago", "Posted 2 hours ago", "yesterday", "last week"
_POSTED_AGO_RE = re.compile(
    r"\b(\d+|an?|one)\s+(minute|min|hour|hr|day|week|month|year)s?\s+ago\b", re.IGNORECASE
)
_UNIT_DAYS = {"minute": 1 / 1440, "min": 1 / 1440, "hour": 1 / 24, "hr": 1 / 24,
              "day": 1, "week": 7, "month": 30, "year": 365}
_POSTED_WORDS = {"just now": 0, "today": 0, "yesterday": 1, "last week": 7,
                 "last month": 30, "last year": 365}


def parse_posted_text(text: Optional[str], now: Optional[datetime] = None) -> Optional[datetime]:
    """Approximate posting time from Upwork's relative text; None when it can't be read."""
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    lowered = text.lower()
    m = _POSTED_AGO_RE.search(lowered)
    if m:
        count = 1 if m.group(1) in ("a", "an", "one") else int(m.group(1))
        return now - timedelta(days=count * _UNIT_DAYS[m.group(2)])
    for phrase, days in _POSTED_WORDS.items():
        if phrase in lowered:
            return now - timedelta(days=days)
    return None


def is_blocked_country(country: Optional[str]) -> bool:
    return bool(country) and _BLOCKED_COUNTRY_RE.search(country.lower()) is not None


def pre_filter(
    *,
    title: str,
    description: str = "",
    budget_amount: Optional[str] = None,
    budget_type: Optional[str] = None,
    posted_at: Optional[datetime] = None,
    posted_text: Optional[str] = None,
    client_country: Optional[str] = None,
    min_budget: Optional[float] = None,
    min_hourly: Optional[float] = None,
    avoid_keywords: Optional[Iterable[str]] = None,
    scored: int = 0,
    score_cap: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Return a skip reason string if the job should not be scored, else None.

    Checks (in order):
      1. Age         — posted_at (or posted_text when posted_at is missing) older than MAX_JOB_AGE_DAYS
      2. Geography   — client country in blocked list (only when known)
      3. Fixed price — below the floor, unless a known placeholder value
      4. Hourly rate — top end of range below the floor
      5. Avoid kw    — any avoid keyword in title or first 400 chars of description
      6. Score cap   — `scored` already reached `score_cap`
    """
    now = now or datetime.now(timezone.utc)

    # 1. Age gate
    posted = posted_at or parse_posted_text(posted_text, now)
    if posted:
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        if posted < now - timedelta(days=MAX_JOB_AGE_DAYS):
            return f"too_old ({(now - posted).days}d)"

    # 2. Geography gate
    if is_blocked_country(client_country):
        return f"blocked_country ({client_country})"

    # 3 & 4. Budget gate
    if budget_amount:
        all_values = [float(v.replace(",", "")) for v in _BUDGET_VALUE_RE.findall(budget_amount)]
        if all_values:
            min_val, max_val = min(all_values), max(all_values)
            if budget_type == "hourly":
                # Check the TOP of the range — what the client is willing to pay
                floor = float(min_hourly) if min_hourly is not None else HOURLY_MIN_TOP_RATE
                if max_val < floor:
                    return f"hourly_top_too_low (${max_val:.0f}/hr < ${floor:.0f})"
            else:
                floor = float(min_budget) if min_budget is not None else FIXED_BUDGET_MIN
                if min_val not in FIXED_BUDGET_PLACEHOLDERS and min_val < floor:
                    return f"budget_too_low (${min_val:.0f} < ${floor:.0f})"

    # 5. Avoid keywords (case-insensitive)
    if avoid_keywords:
        text = f"{title} {(description or '')[:400]}".lower()
        for kw in avoid_keywords:
            if kw and kw.lower() in text:
                return f"avoid_keyword ({kw!r})"

    # 6. Per-run scoring cap
    if score_cap is not None and scored >= score_cap:
        return f"score_cap_reached ({score_cap})"

    return None
