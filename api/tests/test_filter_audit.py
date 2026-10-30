"""Filter audit: skip-reason counts, per-rule pre-filter stats, n<5 rule, read-only loader."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.job_queue import JobQueueItem
from app.models.outcome_event import OutcomeEvent
from app.models.user import User
from app.services.filter_audit import AuditItem, blocked_rule, build_audit, load_items, render_text

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def _item(status, reason=None, days_ago=1, **kw):
    return AuditItem(status=status, rejection_reason=reason, created_at=NOW - timedelta(days=days_ago), **kw)


def test_blocked_rule():
    assert blocked_rule(_item("pre_filtered", "pre_filter:too_old: 9d")) == "pre_filter:too_old"
    assert blocked_rule(_item("pre_filtered", "blocked_country (India)")) == "pre_filter:blocked_country"
    assert blocked_rule(_item("suggested", scored_anyway=True,
                              score_anyway_rule="pre_filter:avoid_keyword")) == "pre_filter:avoid_keyword"
    assert blocked_rule(_item("approved", scored_anyway=True)) == "unknown"
    assert blocked_rule(_item("rejected", "budget_too_low")) is None


def test_skip_reason_counts_window_and_other_texts():
    items = [_item("rejected", "budget_too_low") for _ in range(4)] + [
        _item("rejected", "Budget too low"),                         # legacy label → budget_too_low
        _item("rejected", "other: on-site only"),
        _item("rejected", "on-site only"),                           # legacy free text → other
        _item("rejected", "wrong_skills", days_ago=200),             # outside the window
        _item("approved"),
    ]
    r = build_audit(items, 90, NOW)
    assert r["user_skips"] == 7
    assert r["skip_reasons"]["budget_too_low"] == {"count": 5, "rate": 71.4}
    assert r["skip_reasons"]["other"]["count"] == 2
    assert "wrong_skills" not in r["skip_reasons"]
    assert r["other_texts"] == [{"text": "on-site only", "count": 2}]
    small = build_audit(items[:3], 90, NOW)
    assert small["skip_reasons"]["budget_too_low"] == {"count": 3, "rate": "n<5"}


def test_rule_stats_flag_rules_that_threw_out_good_jobs():
    country = "pre_filter:blocked_country: India"
    items = (
        [_item("pre_filtered", country) for _ in range(4)]
        + [_item("suggested", scored_anyway=True, score_anyway_rule="pre_filter:blocked_country", ai_score=s)
           for s in (82, 45)]
        + [_item("pre_filtered", "too_old (9d)") for _ in range(6)]
    )
    r = build_audit(items, 90, NOW)
    bc = r["pre_filter_rules"]["pre_filter:blocked_country"]
    assert (bc["blocked"], bc["scored_anyway"], bc["scored_anyway_rate"]) == (6, 2, 33.3)
    assert bc["scored_anyway_scores"]["count"] == 2
    assert (bc["scored_anyway_scores"]["min"], bc["scored_anyway_scores"]["max"]) == (45.0, 82.0)
    assert bc["scored_anyway_scores"]["bands"]["70-84"] == 1
    assert (bc["with_score"], bc["good"], bc["good_rate"], bc["flagged"]) == (2, 1, "n<5", True)
    old = r["pre_filter_rules"]["pre_filter:too_old"]
    assert (old["blocked"], old["scored_anyway_rate"], old["flagged"]) == (6, 0.0, False)
    assert r["pre_filter_rules"]["pre_filter:score_cap_reached"]["blocked"] == 0
    assert r["pre_filter_rules"]["pre_filter:score_cap_reached"]["scored_anyway_rate"] == "n<5"
    assert r["flagged_rules"] == ["pre_filter:blocked_country"]
    assert r["pre_filter_blocked"] == 12
    text = render_text(r)
    assert "<- FLAG" in text and "n<5" in text and "pre_filter:too_old" in text


async def test_load_items_reads_score_anyway_rule_from_events(db_session):
    user = User(email=f"audit-{datetime.now().timestamp()}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    blocked = JobQueueItem(user_id=user.id, upwork_url="https://www.upwork.com/jobs/~1", title="a",
                           status="pre_filtered", rejection_reason="pre_filter:too_old: 9d")
    rescored = JobQueueItem(user_id=user.id, upwork_url="https://www.upwork.com/jobs/~2", title="b",
                            status="suggested", ai_score=88)
    legacy = JobQueueItem(user_id=user.id, upwork_url="https://www.upwork.com/jobs/~3", title="c",
                          status="suggested", ai_score=30)
    db_session.add_all([blocked, rescored, legacy])
    await db_session.flush()
    db_session.add_all([
        OutcomeEvent(user_id=user.id, job_queue_id=rescored.id, event_type="score_anyway",
                     meta={"skip_reason": "pre_filter:avoid_keyword"}),
        OutcomeEvent(user_id=user.id, job_queue_id=legacy.id, event_type="score_anyway"),
    ])
    await db_session.commit()

    items = await load_items(db_session, user.id, datetime.now(timezone.utc) - timedelta(days=1))
    by_title = {i.ai_score: i for i in items}
    assert len(items) == 3
    assert by_title[88.0].scored_anyway and by_title[88.0].score_anyway_rule == "pre_filter:avoid_keyword"
    assert by_title[30.0].scored_anyway and by_title[30.0].score_anyway_rule is None
    r = build_audit(items, 1, datetime.now(timezone.utc))
    assert r["pre_filter_rules"]["pre_filter:avoid_keyword"]["good"] == 1
    assert r["pre_filter_rules"]["unknown"]["blocked"] == 1
    assert r["pre_filter_rules"]["pre_filter:too_old"]["blocked"] == 1


def test_script_imports():
    script = Path(__file__).resolve().parents[2] / "scripts" / "filter_audit.py"
    spec = importlib.util.spec_from_file_location("filter_audit_script", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.main) and "--days" in mod.__doc__
