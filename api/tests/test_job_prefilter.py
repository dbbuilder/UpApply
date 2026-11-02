"""The shared pre-filter (app/services/job_prefilter.py): rules, profile floors, posted_text."""
from datetime import datetime, timedelta, timezone

import pytest

from agent.job_discovery import JobDiscoveryAgent
from agent.rss_adapter import RawJob
from app.services.job_prefilter import is_blocked_country, parse_posted_text, pre_filter
from app.services.skip_reasons import PRE_FILTER_CODES, normalise_pre_filter

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _pf(**kw):
    kw.setdefault("title", "Build a FastAPI backend")
    kw.setdefault("now", NOW)
    return pre_filter(**kw)


# ── posted_text ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,days", [
    ("3 days ago", 3), ("Posted 2 hours ago", 2 / 24), ("an hour ago", 1 / 24),
    ("2 weeks ago", 14), ("a month ago", 30), ("yesterday", 1), ("last week", 7),
    ("Posted just now", 0), ("15 minutes ago", 15 / 1440),
])
def test_parse_posted_text(text, days):
    assert parse_posted_text(text, NOW) == NOW - timedelta(days=days)


@pytest.mark.parametrize("text", [None, "", "Fixed-price", "soon"])
def test_parse_posted_text_unreadable(text):
    assert parse_posted_text(text, NOW) is None


def test_posted_text_counts_toward_too_old_when_posted_at_missing():
    assert _pf(posted_text="2 weeks ago") == "too_old (14d)"
    assert _pf(posted_text="3 days ago") is None


def test_posted_at_wins_over_posted_text():
    assert _pf(posted_at=NOW - timedelta(days=1), posted_text="3 weeks ago") is None
    assert _pf(posted_at=NOW - timedelta(days=9), posted_text="1 hour ago") == "too_old (9d)"


def test_naive_posted_at_is_utc():
    assert _pf(posted_at=(NOW - timedelta(days=8)).replace(tzinfo=None)) == "too_old (8d)"


# ── budget floors: profile minimums vs the default floors ─────────────────────

def test_fixed_floor_defaults_to_500():
    assert _pf(budget_amount="$300", budget_type="fixed") == "budget_too_low ($300 < $500)"
    assert _pf(budget_amount="$600", budget_type="fixed") is None


def test_fixed_floor_uses_profile_minimum_budget():
    assert _pf(budget_amount="$600", budget_type="fixed", min_budget=1000) == "budget_too_low ($600 < $1000)"
    assert _pf(budget_amount="$300", budget_type="fixed", min_budget=250) is None


def test_fixed_placeholders_still_pass():
    assert _pf(budget_amount="$5", budget_type="fixed", min_budget=1000) is None
    assert _pf(budget_amount="$100", budget_type=None) is None


def test_hourly_floor_defaults_to_60_on_top_of_range():
    assert _pf(budget_amount="$20 - $45", budget_type="hourly") == "hourly_top_too_low ($45/hr < $60)"
    assert _pf(budget_amount="$20 - $75", budget_type="hourly") is None


def test_hourly_floor_uses_profile_minimum_hourly_rate():
    assert _pf(budget_amount="$40 - $90", budget_type="hourly", min_hourly=100) == "hourly_top_too_low ($90/hr < $100)"
    assert _pf(budget_amount="$30 - $45", budget_type="hourly", min_hourly=40) is None


def test_decimal_profile_minimum_is_accepted():
    from decimal import Decimal
    assert _pf(budget_amount="$700", budget_type="fixed", min_budget=Decimal("800.00")) == "budget_too_low ($700 < $800)"


# ── geography, keywords, cap ─────────────────────────────────────────────────

def test_blocked_country_whole_word():
    assert _pf(client_country="India") == "blocked_country (India)"
    assert _pf(client_country="Dubai, United Arab Emirates") == "blocked_country (Dubai, United Arab Emirates)"
    assert is_blocked_country("Romania") is False  # "oman" inside Romania
    assert is_blocked_country("United States") is False
    assert is_blocked_country(None) is False


def test_avoid_keyword():
    assert _pf(title="WordPress theme tweak", avoid_keywords=["wordpress"]) == "avoid_keyword ('wordpress')"
    assert _pf(avoid_keywords=["", "wordpress"]) is None


def test_score_cap():
    assert _pf(scored=25, score_cap=25) == "score_cap_reached (25)"
    assert _pf(scored=24, score_cap=25) is None
    assert _pf(scored=999) is None


def test_every_rule_maps_to_a_canonical_code():
    for raw in ["too_old (9d)", "blocked_country (India)", "budget_too_low ($300 < $500)",
                "hourly_top_too_low ($45/hr < $60)", "avoid_keyword ('x')", "score_cap_reached (25)"]:
        code, _ = normalise_pre_filter(raw)
        assert code in PRE_FILTER_CODES
    assert "pre_filter:below_threshold" in PRE_FILTER_CODES


# ── the retired agent uses the same rules, with the profile minimums ─────────

def _agent(min_budget=None, min_hourly=None):
    agent = JobDiscoveryAgent(api_base="http://x", token="t")
    agent._min_budget, agent._min_hourly = min_budget, min_hourly
    agent._stats = {"jobs_scored": 0}
    return agent


def _raw(budget, kind):
    return RawJob(title="API work", description="", upwork_url="https://www.upwork.com/jobs/~01ab",
                  upwork_uid="~01ab", posted_date=None, budget_amount=budget, budget_type=kind, skills=[])


def test_agent_pre_filter_honours_profile_minimums():
    assert _agent()._pre_filter(_raw("$600", "fixed")) is None
    assert _agent(min_budget=1000)._pre_filter(_raw("$600", "fixed")) == "budget_too_low ($600 < $1000)"
    assert _agent(min_hourly=100)._pre_filter(_raw("$40 - $90", "hourly")) == "hourly_top_too_low ($90/hr < $100)"


def test_malformed_untrusted_values_do_not_raise():
    assert parse_posted_text("99999 years ago") is None
    assert parse_posted_text("9" * 200 + " days ago") is None
    assert _pf(budget_amount="$,") is None


def test_max_age_days_overrides_the_default():
    assert _pf(posted_text="10 days ago") == "too_old (10d)"
    assert _pf(posted_text="10 days ago", max_age_days=14) is None
    assert _pf(posted_text="3 weeks ago", max_age_days=14) == "too_old (21d)"
