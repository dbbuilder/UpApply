"""GuardrailChecker — enforces hard limits before autonomous agent actions.

All limits are checked before any irreversible action. The checker NEVER
bypasses a failing guard — it raises GuardrailViolation instead.

Guards checked (in order):
  1. Agent enabled (master switch)
  2. Pause window (quiet hours)
  3. Daily proposal cap (count submitted today)
  4. Connects reserve (estimated balance vs. minimum)
  5. Bid amount (per-job check before confirming)
  6. Score threshold (minimum quality gate)

Each guard is independently checked so the violation message is precise.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_queue import JobQueueItem
from app.models.user_guardrail_config import UserGuardrailConfig

logger = logging.getLogger(__name__)


class GuardrailViolation(Exception):
    """Raised when a guardrail check fails.

    Includes a human-readable reason suitable for displaying in the digest
    or logging for support.
    """
    def __init__(self, guard: str, reason: str) -> None:
        self.guard = guard
        self.reason = reason
        super().__init__(f"[{guard}] {reason}")


@dataclass
class GuardrailResult:
    """Summary returned by check_all — allows callers to proceed or report."""
    passed: bool
    violations: list[GuardrailViolation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def first_blocking(self) -> Optional[GuardrailViolation]:
        return self.violations[0] if self.violations else None


async def get_or_create_guardrails(
    user_id: str, db: AsyncSession
) -> UserGuardrailConfig:
    """Return the user's guardrail config, creating defaults if absent."""
    result = await db.execute(
        select(UserGuardrailConfig).where(UserGuardrailConfig.user_id == user_id)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = UserGuardrailConfig(user_id=user_id)
        db.add(cfg)
        await db.flush()
        logger.info("Created default guardrail config for user %s", user_id)
    return cfg


async def count_proposals_today(user_id: str, db: AsyncSession) -> int:
    """Count queue items confirmed for submission today (UTC)."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(func.count()).where(
            JobQueueItem.user_id == user_id,
            JobQueueItem.confirmed_at >= today_start,
        )
    )
    return result.scalar() or 0


# ── Individual guards ────────────────────────────────────────────────────────

def check_enabled(cfg: UserGuardrailConfig) -> None:
    if not cfg.enabled:
        raise GuardrailViolation("ENABLED", "Agent is disabled by user. Enable it in guardrail settings.")


def check_pause_window(cfg: UserGuardrailConfig) -> None:
    if cfg.pause_start_hour is None or cfg.pause_end_hour is None:
        return
    now_hour = datetime.now(timezone.utc).hour
    start, end = cfg.pause_start_hour, cfg.pause_end_hour
    if start <= end:
        in_window = start <= now_hour < end
    else:  # wraps midnight
        in_window = now_hour >= start or now_hour < end
    if in_window:
        raise GuardrailViolation(
            "PAUSE_WINDOW",
            f"Agent is in quiet window ({start:02d}:00–{end:02d}:00 UTC). Will resume after.",
        )


def check_daily_cap(cfg: UserGuardrailConfig, proposals_today: int) -> None:
    if proposals_today >= cfg.max_proposals_per_day:
        raise GuardrailViolation(
            "DAILY_CAP",
            f"Daily proposal cap reached ({proposals_today}/{cfg.max_proposals_per_day}). "
            f"Resets at midnight UTC.",
        )


def check_connects_reserve(cfg: UserGuardrailConfig) -> Optional[str]:
    """Returns a warning string if connects are low but not blocking.
    Raises GuardrailViolation if balance is below reserve."""
    if cfg.connects_balance is None:
        return None  # Unknown balance — skip check
    remaining = cfg.connects_balance - cfg.min_connects_reserve
    if remaining < 0:
        raise GuardrailViolation(
            "CONNECTS_RESERVE",
            f"Connects balance ({cfg.connects_balance}) is below reserve ({cfg.min_connects_reserve}). "
            f"Top up Upwork connects or lower the reserve.",
        )
    if remaining < 10:
        return f"Low connects: {cfg.connects_balance} remaining (reserve={cfg.min_connects_reserve})"
    return None


def check_bid_amount(
    cfg: UserGuardrailConfig,
    bid_amount: Optional[float],
    is_hourly: bool,
) -> None:
    if bid_amount is None:
        return
    cap = float(cfg.max_bid_hourly) if is_hourly and cfg.max_bid_hourly else None
    if cap is None:
        cap = float(cfg.max_bid_fixed) if not is_hourly and cfg.max_bid_fixed else None
    if cap is not None and bid_amount > cap:
        rate_type = "hourly" if is_hourly else "fixed"
        raise GuardrailViolation(
            "BID_CAP",
            f"Bid ${bid_amount:.2f} exceeds {rate_type} cap ${cap:.2f}. "
            f"Adjust the bid or raise the cap in guardrail settings.",
        )


def check_score_threshold(cfg: UserGuardrailConfig, score: float) -> None:
    if score < cfg.min_score_threshold:
        raise GuardrailViolation(
            "SCORE_THRESHOLD",
            f"Job score {score:.1f} is below autonomous submission threshold "
            f"{cfg.min_score_threshold:.1f}. Needs manual approval.",
        )


# ── Composite check ──────────────────────────────────────────────────────────

async def check_submission_guards(
    user_id: str,
    db: AsyncSession,
    score: Optional[float] = None,
    bid_amount: Optional[float] = None,
    is_hourly: bool = True,
) -> GuardrailResult:
    """Run all submission-time guards. Returns GuardrailResult (never raises).

    Callers should check result.passed before proceeding. If False, read
    result.violations for the specific blockers.
    """
    cfg = await get_or_create_guardrails(user_id, db)
    violations: list[GuardrailViolation] = []
    warnings: list[str] = []

    for guard_fn, args in [
        (check_enabled, (cfg,)),
        (check_pause_window, (cfg,)),
    ]:
        try:
            guard_fn(*args)
        except GuardrailViolation as v:
            violations.append(v)

    if not violations:
        # Only check these if agent is enabled + not in pause window
        try:
            proposals_today = await count_proposals_today(user_id, db)
            check_daily_cap(cfg, proposals_today)
        except GuardrailViolation as v:
            violations.append(v)

        try:
            warn = check_connects_reserve(cfg)
            if warn:
                warnings.append(warn)
        except GuardrailViolation as v:
            violations.append(v)

        if score is not None:
            try:
                check_score_threshold(cfg, score)
            except GuardrailViolation as v:
                violations.append(v)

        if bid_amount is not None:
            try:
                check_bid_amount(cfg, bid_amount, is_hourly)
            except GuardrailViolation as v:
                violations.append(v)

    if violations:
        logger.warning(
            "Guardrail violations for user %s: %s",
            user_id, [str(v) for v in violations],
        )

    return GuardrailResult(passed=not violations, violations=violations, warnings=warnings)
