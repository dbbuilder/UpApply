"""Canonical skip reasons for job-queue items (user passes and automatic pre-filter blocks).

Stored in job_queue.rejection_reason as "<code>" or "<code>: <free text>". Anything outside the
list is stored as "other" with the text kept, so new reasons surface in scripts/filter_audit.py.
Values written before this module (free text, raw pre-filter strings such as
"blocked_country (India)") are mapped at read time by parse_stored().
"""
import re
from typing import Optional

OTHER = "other"

# Reasons a user can give when passing on a suggestion (the extension's quick choices).
USER_REASONS = (
    "budget_too_low",
    "wrong_skills",
    "scope_unclear",
    "too_large",
    "client_risk",
    "too_many_proposals",
    "timing",
    "not_interested",
    "duplicate",
    OTHER,
)

# The automatic pre-filter rules in agent/job_discovery.py JobDiscoveryAgent._pre_filter().
PRE_FILTER_RULES = (
    "too_old",
    "blocked_country",
    "budget_too_low",
    "hourly_top_too_low",
    "avoid_keyword",
    "score_cap_reached",
)
PRE_FILTER_PREFIX = "pre_filter:"
PRE_FILTER_CODES = tuple(PRE_FILTER_PREFIX + r for r in PRE_FILTER_RULES)
ALL_CODES = USER_REASONS + PRE_FILTER_CODES

# The extension's old free-text choices, mapped when the stored value matches exactly.
LEGACY_LABELS = {
    "budget too low": "budget_too_low",
    "not my specialty": "wrong_skills",
    "too large / long": "too_large",
    "client looks risky": "client_risk",
    "already applied": "duplicate",
    "other": OTHER,
}

# Raw pre-filter string: "rule" or "rule (detail)".
_RAW_RULE_RE = re.compile(r"^([a-z_]+)(?: \((.*)\))?$", re.S)


def encode(code: str, text: Optional[str] = None) -> str:
    text = (text or "").strip()
    return f"{code}: {text}" if text else code


def _split_coded(raw: str, codes) -> Optional[tuple[str, Optional[str]]]:
    """'<code>' or '<code>: text' for a code in codes, else None."""
    head, sep, rest = raw.partition(":")
    if raw.startswith(PRE_FILTER_PREFIX):
        head2, sep, rest = rest.partition(":")
        head = PRE_FILTER_PREFIX + head2
    head = head.strip()
    if head not in codes:
        return None
    return head, (rest.strip() or None) if sep else None


def normalise_user_reason(raw: Optional[str]) -> Optional[tuple[str, Optional[str]]]:
    """A user's pass reason → (code, free text). None when no reason was given."""
    raw = (raw or "").strip()
    if not raw:
        return None
    coded = _split_coded(raw, USER_REASONS)
    if coded:
        return coded
    legacy = LEGACY_LABELS.get(raw.lower())
    if legacy:
        return legacy, None
    return OTHER, raw


def normalise_pre_filter(raw: Optional[str]) -> Optional[tuple[str, Optional[str]]]:
    """The pre-filter's skip string ("blocked_country (India)") → (code, detail)."""
    raw = (raw or "").strip()
    if not raw:
        return None
    coded = _split_coded(raw, PRE_FILTER_CODES)
    if coded:
        return coded
    m = _RAW_RULE_RE.match(raw)
    if m and m.group(1) in PRE_FILTER_RULES:
        return PRE_FILTER_PREFIX + m.group(1), m.group(2) or None
    return OTHER, raw


def parse_stored(raw: Optional[str], status: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """A stored rejection_reason → (code, free text), mapping legacy values.

    status 'pre_filtered' reads raw rule strings as pre-filter codes; everything else as a
    user reason. A canonical pre_filter code is recognised whatever the status.
    """
    raw = (raw or "").strip()
    if not raw:
        return None, None
    coded = _split_coded(raw, PRE_FILTER_CODES)
    if coded:
        return coded
    parsed = normalise_pre_filter(raw) if status == "pre_filtered" else normalise_user_reason(raw)
    return parsed or (None, None)
