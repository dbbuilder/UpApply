"""Results report: reply/interview rates of v2-engine proposals vs the 90 days before.

summarise() and build_report() are pure; load_rows() reads one user's proposals (read-only),
linking each proposal to its sent letter with outcomes.find_sent_letter, the same link outcome
sync uses to credit facts. Used by scripts/outcome_report.py.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cover_letter import CoverLetter
from app.models.job import Job
from app.models.proposal import Proposal
from app.models.proposal_stage_event import ProposalStageEvent
from app.services.outcomes import NO_RESPONSE_AFTER, find_sent_letter
from app.services.proposal_status import UNKNOWN

BASELINE_DAYS = 90
MIN_DENOMINATOR = 5
PENDING_STAGES = frozenset({"submitted", "viewed"})
REPLY_OR_BETTER = frozenset({"replied", "interview", "hired"})
FUNNEL = {
    "viewed": frozenset({"viewed"}) | REPLY_OR_BETTER,
    "replied": REPLY_OR_BETTER,
    "interview": frozenset({"interview", "hired"}),
    "hired": frozenset({"hired"}),
}
# proposals.outcome (forward-only, set by outcome sync before stages existed) → stage
OUTCOME_TO_STAGE = {
    "viewed": "viewed", "replied": "replied", "interviewed": "interview",
    "hired": "hired", "declined": "declined",
}
BANDS = ("<50", "50-69", "70-84", "85+", "no score")


@dataclass
class ReportRow:
    sent_at: datetime
    stage: str
    outcome: Optional[str] = None
    # (from_stage, to_stage, at) ledger rows; from_stage None = the row's creation
    ledger: list[tuple[Optional[str], str, datetime]] = field(default_factory=list)
    match_score: Optional[float] = None
    is_v2: bool = False


def observed_stages(row: ReportRow) -> set[str]:
    """Every known stage the proposal is known to have reached."""
    seen = {row.stage, *(to for _, to, _ in row.ledger), OUTCOME_TO_STAGE.get(row.outcome or "")}
    return {s for s in seen if s and s != UNKNOWN}


def classify(row: ReportRow, now: datetime) -> str:
    """'unknown' (no known stage), 'pending' (no result yet, under 14 days old) or 'counted'."""
    seen = observed_stages(row)
    if not seen:
        return "unknown"
    if seen <= PENDING_STAGES and now - row.sent_at < NO_RESPONSE_AFTER:
        return "pending"
    return "counted"


def days_to_first_reply(row: ReportRow) -> Optional[float]:
    """Submission → first ledger transition into a reply or better (creation rows excluded)."""
    hits = [at for frm, to, at in row.ledger if frm is not None and to in REPLY_OR_BETTER]
    if not hits:
        return None
    return max(0.0, (min(hits) - row.sent_at).total_seconds() / 86400)


def _rate(count: int, denominator: int):
    return "n<5" if denominator < MIN_DENOMINATOR else round(100 * count / denominator, 1)


def summarise(rows: list[ReportRow], now: datetime) -> dict:
    kinds = [classify(r, now) for r in rows]
    counted = [r for r, k in zip(rows, kinds) if k == "counted"]
    out = {
        "proposals": len(rows),
        "sent": len(counted),
        "pending": kinds.count("pending"),
        "unknown": kinds.count("unknown"),
    }
    for name, stages in FUNNEL.items():
        n = sum(1 for r in counted if observed_stages(r) & stages)
        out[name] = n
        out[f"{name}_rate"] = _rate(n, len(counted))
    timings = [d for d in (days_to_first_reply(r) for r in rows) if d is not None]
    out["median_days_to_reply"] = round(median(timings), 1) if timings else None
    out["reply_timings"] = len(timings)
    return out


def band(score: Optional[float]) -> str:
    if score is None:
        return "no score"
    score = float(score)
    if score < 50:
        return "<50"
    if score < 70:
        return "50-69"
    if score < 85:
        return "70-84"
    return "85+"


def _group(rows: list[ReportRow], now: datetime) -> dict:
    return {
        "overall": summarise(rows, now),
        "by_match_score": {b: summarise([r for r in rows if band(r.match_score) == b], now) for b in BANDS},
    }


def build_report(rows: list[ReportRow], since: datetime, now: datetime) -> dict:
    """v2 group: v2 letters sent on/after since. Baseline: non-v2 sent in the 90 days before."""
    start = since - timedelta(days=BASELINE_DAYS)
    v2 = [r for r in rows if r.is_v2 and r.sent_at >= since]
    baseline = [r for r in rows if not r.is_v2 and start <= r.sent_at < since]
    return {
        "since": since.isoformat(),
        "baseline_from": start.isoformat(),
        "generated_at": now.isoformat(),
        "v2": _group(v2, now),
        "baseline": _group(baseline, now),
    }


def _fmt(value) -> str:
    return "n<5" if value == "n<5" else f"{value}%"


def render_text(report: dict) -> str:
    lines = [
        f"Outcome report (generated {report['generated_at'][:10]})",
        f"v2 engine: proposals sent since {report['since'][:10]}",
        f"Baseline:  other proposals sent {report['baseline_from'][:10]} to {report['since'][:10]}",
        "",
    ]
    header = f"{'group':<22}{'sent':>6}{'viewed':>9}{'replied':>9}{'interview':>11}{'hired':>8}" \
             f"{'pending':>9}{'unknown':>9}{'median d':>10}"
    for key, title in (("v2", "v2 engine"), ("baseline", "prior 90 days")):
        group = report[key]
        lines += [title, header]
        for label, s in [("all", group["overall"])] + [
            (f"  score {b}", s) for b, s in group["by_match_score"].items() if s["proposals"]
        ]:
            med = "-" if s["median_days_to_reply"] is None else f"{s['median_days_to_reply']} ({s['reply_timings']})"
            lines.append(
                f"{label:<22}{s['sent']:>6}{_fmt(s['viewed_rate']):>9}{_fmt(s['replied_rate']):>9}"
                f"{_fmt(s['interview_rate']):>11}{_fmt(s['hired_rate']):>8}{s['pending']:>9}"
                f"{s['unknown']:>9}{med:>10}"
            )
        lines.append("")
    lines.append("Rates are over 'sent' (pending and unknown excluded); n<5 = too few to show a rate.")
    return "\n".join(lines)


async def first_v2_letter_at(db: AsyncSession, user_id: str) -> Optional[datetime]:
    return (await db.execute(
        select(func.min(CoverLetter.created_at))
        .where(CoverLetter.user_id == user_id, CoverLetter.prompt_version == "v2")
    )).scalar_one_or_none()


async def load_rows(db: AsyncSession, user_id: str) -> tuple[list[ReportRow], int]:
    """Report rows for a user's dated proposals, and the count skipped for having no
    submitted_at (ChatGPT and contract imports: their created_at is the import date)."""
    props = (await db.execute(
        select(Proposal, Job.match_score)
        .outerjoin(Job, Proposal.job_id == Job.id)
        .where(Proposal.user_id == user_id)
    )).all()
    ledger: dict[str, list] = {}
    for ev in (await db.execute(
        select(ProposalStageEvent).where(ProposalStageEvent.user_id == user_id)
    )).scalars():
        ledger.setdefault(ev.proposal_id, []).append((ev.from_stage, ev.to_stage, ev.created_at))
    rows, undated = [], 0
    for prop, score in props:
        if prop.submitted_at is None:
            undated += 1
            continue
        letter = await find_sent_letter(db, prop.user_id, prop.job_id)
        rows.append(ReportRow(
            sent_at=prop.submitted_at, stage=prop.stage, outcome=prop.outcome,
            ledger=ledger.get(prop.id, []),
            match_score=float(score) if score is not None else None,
            is_v2=bool(letter and letter.prompt_version == "v2"),
        ))
    return rows, undated
