"""Client trust card: how much to trust the client behind a job post.

Kept separate from the 0-100 match score: the match score says how well a job
fits the user, the trust card says what the client's Upwork history shows.
Nothing here feeds back into the match score.

``assess_client_trust`` is a pure function. Missing data is always neutral:
a signal is only ``caution`` when the data is present and points that way.
Labels describe what the data shows and never accuse the client.

Rule table (constants below):

| Signal         | positive                       | caution                                              |
|----------------|--------------------------------|------------------------------------------------------|
| Payment        | verified                       | explicitly not verified                              |
| Total spent    | >= HIGH_SPEND_USD              | $0 and no hires (or hires unknown)                   |
| Hire rate      | >= GOOD_HIRE_RATE_PCT          | < LOW_HIRE_RATE_PCT with >= MANY_JOBS_POSTED posted   |
| Rating         | >= GOOD_RATING                 | > 0 and < LOW_RATING                                 |
| Proposals      | -                              | >= MANY_PROPOSALS already                            |
| Job age        | -                              | posted more than LONG_OPEN_DAYS ago                  |
| Reposted       | -                              | same title seen in the last REPOST_WINDOW_DAYS days  |
| Location, member since | informational (neutral) only                                          |

Tier: >= SUSPICIOUS_MIN_CAUTIONS cautions -> "Suspicious"; any caution ->
"Proceed with Caution"; otherwise "High Confidence".
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TIER_HIGH = "High Confidence"
TIER_CAUTION = "Proceed with Caution"
TIER_SUSPICIOUS = "Suspicious"

HIGH_SPEND_USD = 10_000        # lifetime spend that shows an established client
GOOD_HIRE_RATE_PCT = 70        # hires on most of the jobs they post
LOW_HIRE_RATE_PCT = 30         # rarely hires ...
MANY_JOBS_POSTED = 5           # ... across enough jobs for the rate to mean something
GOOD_RATING = 4.5              # out of 5
LOW_RATING = 4.0
MANY_PROPOSALS = 50            # crowded: "50+" on Upwork
LONG_OPEN_DAYS = 30            # still open a month after posting
REPOST_WINDOW_DAYS = 30
SUSPICIOUS_MIN_CAUTIONS = 3

POSITIVE, NEUTRAL, CAUTION = "positive", "neutral", "caution"


# ── Parsing helpers (tolerant of Upwork's display strings) ───────────────────

def _first(info: Dict[str, Any], *keys: str) -> Any:
    """First non-empty value under any of ``keys`` (snake_case and camelCase both occur)."""
    for key in keys:
        value = info.get(key)
        if value is not None and value != "":
            return value
    return None


def _parse_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if "unverified" in text or "not verified" in text or text in ("false", "no"):
            return False
        if "verified" in text or text in ("true", "yes"):
            return True
    return None


def _parse_number(value: Any) -> Optional[float]:
    """First number in ``value``; honours K/M suffixes ("$10K+" -> 10000)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?", value)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").lower()
    return number * {"k": 1_000, "m": 1_000_000}.get(suffix, 1)


def _parse_rating(value: Any) -> Optional[float]:
    rating = _parse_number(value)
    return rating if rating is not None and 0 <= rating <= 5 else None


def _fmt_usd(amount: float) -> str:
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M".replace(".0M", "M")
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K".replace(".0K", "K")
    return f"${amount:,.0f}"


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def normalise_title(title: Optional[str]) -> str:
    """Lowercase, punctuation-free, single-spaced title used for repost matching."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split())


def job_key(upwork_url: Optional[str]) -> str:
    """Stable identity for a job URL: the Upwork ``~0...`` id when present."""
    url = (upwork_url or "").strip()
    match = re.search(r"~0?([0-9a-zA-Z]{10,})", url)
    if match:
        return match.group(1).lower()
    return url.split("?")[0].split("#")[0].rstrip("/").lower()


# ── The pure assessment ──────────────────────────────────────────────────────

def assess_client_trust(
    client_info: Optional[Dict[str, Any]],
    *,
    posted_at: Optional[datetime] = None,
    repost_count: int = 0,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return ``{tier, signals: [{label, value, effect}], notes}`` for one job."""
    info = client_info or {}
    now = _as_utc(now or datetime.now(timezone.utc))
    signals: List[Dict[str, str]] = []

    def add(label: str, value: str, effect: str) -> None:
        signals.append({"label": label, "value": value, "effect": effect})

    verified = _parse_bool(_first(info, "payment_verified", "paymentVerified"))
    if verified is True:
        add("Payment method", "Verified", POSITIVE)
    elif verified is False:
        add("Payment method", "Not verified yet", CAUTION)

    hires = _parse_number(_first(info, "total_hires", "totalHires", "hires"))
    spent = _parse_number(_first(info, "total_spent", "totalSpent"))
    if spent is not None:
        if spent >= HIGH_SPEND_USD:
            add("Total spent", f"{_fmt_usd(spent)} on Upwork", POSITIVE)
        elif spent == 0 and not hires:
            add("Total spent", "No spend or hires on Upwork yet", CAUTION)
        else:
            add("Total spent", f"{_fmt_usd(spent)} on Upwork", NEUTRAL)

    hire_rate = _parse_number(_first(info, "hire_rate", "hireRate"))
    jobs_posted = _parse_number(_first(info, "jobs_posted", "jobsPosted"))
    if hire_rate is not None and 0 <= hire_rate <= 100:
        posted_text = f" across {int(jobs_posted)} jobs" if jobs_posted is not None else ""
        value = f"{int(hire_rate)}%{posted_text}"
        if hire_rate >= GOOD_HIRE_RATE_PCT:
            add("Hire rate", value, POSITIVE)
        elif hire_rate < LOW_HIRE_RATE_PCT and jobs_posted is not None and jobs_posted >= MANY_JOBS_POSTED:
            add("Hire rate", value, CAUTION)
        else:
            add("Hire rate", value, NEUTRAL)

    rating = _parse_rating(_first(info, "rating"))
    if rating is not None:
        if rating == 0:
            add("Client rating", "No reviews yet", NEUTRAL)
        elif rating >= GOOD_RATING:
            add("Client rating", f"{rating:.1f} of 5", POSITIVE)
        elif rating < LOW_RATING:
            add("Client rating", f"{rating:.1f} of 5", CAUTION)
        else:
            add("Client rating", f"{rating:.1f} of 5", NEUTRAL)

    proposals = _parse_number(_first(info, "proposals", "proposals_count", "proposalsCount"))
    if proposals is not None:
        effect = CAUTION if proposals >= MANY_PROPOSALS else NEUTRAL
        add("Proposals so far", f"{int(proposals)}+" if effect == CAUTION else str(int(proposals)), effect)

    if posted_at is not None:
        age_days = (now - _as_utc(posted_at)).days
        if age_days > LONG_OPEN_DAYS:
            add("Posted", f"{age_days} days ago and still open", CAUTION)

    if repost_count > 0:
        times = "once" if repost_count == 1 else f"{repost_count} times"
        add("Reposted", f"Same title seen {times} in the last {REPOST_WINDOW_DAYS} days", CAUTION)

    location = _first(info, "location", "country")
    if isinstance(location, str):
        add("Location", location.strip(), NEUTRAL)
    member_since = _first(info, "member_since", "memberSince")
    if isinstance(member_since, str):
        add("Member since", member_since.strip(), NEUTRAL)

    cautions = sum(1 for s in signals if s["effect"] == CAUTION)
    if cautions >= SUSPICIOUS_MIN_CAUTIONS:
        tier = TIER_SUSPICIOUS
    elif cautions:
        tier = TIER_CAUTION
    else:
        tier = TIER_HIGH

    notes: List[str] = []
    if not any(s["effect"] != NEUTRAL for s in signals):
        notes.append("Little client history was available, so this card is based on limited data.")
    return {"tier": tier, "signals": signals, "notes": notes}


# ── Repost detection (DB) ────────────────────────────────────────────────────

async def recent_title_index(
    db: AsyncSession, user_id: str, now: Optional[datetime] = None
) -> Dict[str, Set[str]]:
    """Map normalised title -> job keys the user has seen in jobs or job_queue recently.

    Titles only: client_info carries no client identifier, so a repost cannot
    be tied to the same client.
    """
    from app.models.job import Job
    from app.models.job_queue import JobQueueItem

    since = _as_utc(now or datetime.now(timezone.utc)) - timedelta(days=REPOST_WINDOW_DAYS)
    index: Dict[str, Set[str]] = {}
    for model in (Job, JobQueueItem):
        rows = await db.execute(
            select(model.title, model.upwork_url).where(
                model.user_id == user_id, model.created_at >= since
            )
        )
        for title, url in rows.all():
            norm = normalise_title(title)
            if norm:
                index.setdefault(norm, set()).add(job_key(url))
    return index


def count_reposts(index: Dict[str, Set[str]], title: Optional[str], upwork_url: Optional[str]) -> int:
    """Other jobs in ``index`` with the same normalised title; 0 without a URL to exclude itself."""
    if not upwork_url:
        return 0
    return len(index.get(normalise_title(title), set()) - {job_key(upwork_url)})


async def client_trust_for(
    db: AsyncSession,
    user_id: str,
    *,
    client_info: Optional[Dict[str, Any]],
    title: Optional[str],
    upwork_url: Optional[str],
    posted_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Trust card for one job, including repost detection."""
    reposts = 0
    if upwork_url:
        reposts = count_reposts(await recent_title_index(db, user_id), title, upwork_url)
    return assess_client_trust(client_info, posted_at=posted_at, repost_count=reposts)


def trust_cards_for(
    index: Dict[str, Set[str]], items: Iterable[Any]
) -> List[Dict[str, Any]]:
    """Trust cards for many rows (with ``client_info``, ``title``, ``upwork_url``) from one index."""
    return [
        assess_client_trust(
            item.client_info,
            posted_at=getattr(item, "posted_date", None),
            repost_count=count_reposts(index, item.title, item.upwork_url),
        )
        for item in items
    ]
