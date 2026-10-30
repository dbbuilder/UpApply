"""Filter audit: why jobs were skipped, and whether the automatic pre-filter threw out good ones.

build_audit() and render_text() are pure; load_items() reads one user's job-queue items and
their score_anyway events (read-only). Used by scripts/filter_audit.py.

A pre-filter block is an item still at status pre_filtered, or one with a score_anyway outcome
event (score-anyway clears rejection_reason, so its rule is read from the event's meta;
events written before that meta existed count under "unknown").
"""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_queue import JobQueueItem
from app.models.outcome_event import OutcomeEvent
from app.services.outcome_report import BANDS, MIN_DENOMINATOR, band
from app.services.skip_reasons import OTHER, PRE_FILTER_CODES, USER_REASONS, parse_stored

GOOD_SCORE = 70
UNKNOWN_RULE = "unknown"
MAX_OTHER_TEXTS = 10


@dataclass
class AuditItem:
    status: str
    rejection_reason: Optional[str]
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    ai_score: Optional[float] = None
    scored_anyway: bool = False
    # the score_anyway event's meta["skip_reason"]; None on events written before it existed
    score_anyway_rule: Optional[str] = None


def _pct(count: int, denominator: int):
    return "n<5" if denominator < MIN_DENOMINATOR else round(100 * count / denominator, 1)


def blocked_rule(item: AuditItem) -> Optional[str]:
    """The pre-filter code that blocked this item, or None when it was never blocked."""
    if item.scored_anyway:
        return item.score_anyway_rule or UNKNOWN_RULE
    if item.status == "pre_filtered":
        return parse_stored(item.rejection_reason, item.status)[0] or UNKNOWN_RULE
    return None


def _rule_summary(items: list[AuditItem]) -> dict:
    scores = [float(i.ai_score) for i in items if i.ai_score is not None]
    rescored = [float(i.ai_score) for i in items if i.scored_anyway and i.ai_score is not None]
    good = sum(1 for s in scores if s >= GOOD_SCORE)
    n_anyway = sum(1 for i in items if i.scored_anyway)
    return {
        "blocked": len(items),
        "scored_anyway": n_anyway,
        "scored_anyway_rate": _pct(n_anyway, len(items)),
        "scored_anyway_scores": {
            "count": len(rescored),
            "min": min(rescored) if rescored else None,
            "median": median(rescored) if rescored else None,
            "max": max(rescored) if rescored else None,
            "bands": {b: sum(1 for s in rescored if band(s) == b) for b in BANDS if b != "no score"},
        },
        "with_score": len(scores),
        "good": good,
        "good_rate": _pct(good, len(scores)),
        "flagged": good > 0,
    }


def build_audit(items: list[AuditItem], days: int, now: datetime) -> dict:
    start = now - timedelta(days=days)
    skips = [i for i in items if i.status == "rejected" and (i.reviewed_at or i.created_at) >= start]
    blocked: dict[str, list[AuditItem]] = {}
    for item in items:
        rule = blocked_rule(item)
        if rule and item.created_at >= start:
            blocked.setdefault(rule, []).append(item)

    codes, other_texts = Counter(), Counter()
    for item in skips:
        code, text = parse_stored(item.rejection_reason, item.status)
        codes[code or "none"] += 1
        if code == OTHER and text:
            other_texts[text] += 1
    skip_reasons = {
        code: {"count": codes[code], "rate": _pct(codes[code], len(skips))}
        for code in [*USER_REASONS, "none"] if codes[code]
    }

    rules = {r: _rule_summary(blocked.get(r, [])) for r in PRE_FILTER_CODES}
    for extra in sorted(set(blocked) - set(PRE_FILTER_CODES)):
        rules[extra] = _rule_summary(blocked[extra])
    return {
        "days": days,
        "from": start.isoformat(),
        "generated_at": now.isoformat(),
        "user_skips": len(skips),
        "skip_reasons": skip_reasons,
        "other_texts": [{"text": t, "count": c} for t, c in other_texts.most_common(MAX_OTHER_TEXTS)],
        "pre_filter_blocked": sum(len(v) for v in blocked.values()),
        "pre_filter_rules": rules,
        "flagged_rules": [r for r, s in rules.items() if s["flagged"]],
    }


def _fmt(value) -> str:
    return "n<5" if value == "n<5" else f"{value}%"


def render_text(report: dict) -> str:
    lines = [
        f"Filter audit (generated {report['generated_at'][:10]}, last {report['days']} days "
        f"from {report['from'][:10]})",
        "",
        f"User skips: {report['user_skips']}",
    ]
    for code, s in report["skip_reasons"].items():
        lines.append(f"  {code:<22}{s['count']:>5}{_fmt(s['rate']):>8}")
    if report["other_texts"]:
        lines.append("  'other' reasons given:")
        lines += [f"    {o['count']:>3}  {o['text']}" for o in report["other_texts"]]
    lines += [
        "",
        f"Pre-filter blocks: {report['pre_filter_blocked']}",
        f"{'rule':<32}{'blocked':>8}{'anyway':>8}{'anyway%':>9}{'scored':>8}{'>=70':>6}{'>=70%':>8}"
        f"  scored-anyway scores",
    ]
    for rule, s in report["pre_filter_rules"].items():
        d = s["scored_anyway_scores"]
        dist = "-" if not d["count"] else (
            f"min {d['min']:.0f} / median {d['median']:.0f} / max {d['max']:.0f}  "
            + " ".join(f"{b}:{n}" for b, n in d["bands"].items() if n)
        )
        flag = "  <- FLAG" if s["flagged"] else ""
        lines.append(
            f"{rule:<32}{s['blocked']:>8}{s['scored_anyway']:>8}{_fmt(s['scored_anyway_rate']):>9}"
            f"{s['with_score']:>8}{s['good']:>6}{_fmt(s['good_rate']):>8}  {dist}{flag}"
        )
    lines.append("")
    if report["flagged_rules"]:
        lines.append(f"Flagged (blocked at least one job that scored >= {GOOD_SCORE}): "
                     + ", ".join(report["flagged_rules"]))
    else:
        lines.append(f"No rule blocked a job that scored >= {GOOD_SCORE}.")
    lines.append("'scored' = blocked items with an ai_score (usually only score-anyway ones); "
                 "n<5 = too few to show a rate.")
    return "\n".join(lines)


async def load_items(db: AsyncSession, user_id: str, since: datetime) -> list[AuditItem]:
    """The user's queue items created or reviewed since `since`, with their score_anyway events."""
    anyway: dict[str, Optional[str]] = {}
    for job_queue_id, meta in (await db.execute(
        select(OutcomeEvent.job_queue_id, OutcomeEvent.meta)
        .where(OutcomeEvent.user_id == user_id, OutcomeEvent.event_type == "score_anyway")
    )).all():
        if job_queue_id:
            anyway[job_queue_id] = (meta or {}).get("skip_reason") or anyway.get(job_queue_id)
    rows = (await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.user_id == user_id,
            or_(JobQueueItem.created_at >= since, JobQueueItem.reviewed_at >= since),
        )
    )).scalars()
    return [
        AuditItem(
            status=r.status, rejection_reason=r.rejection_reason, created_at=r.created_at,
            reviewed_at=r.reviewed_at, ai_score=r.ai_score,
            scored_anyway=r.id in anyway, score_anyway_rule=anyway.get(r.id),
        )
        for r in rows
    ]
