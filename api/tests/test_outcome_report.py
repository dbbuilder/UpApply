"""Results report: pure aggregation and the read-only loader (v2 link via find_sent_letter)."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.cover_letter import CoverLetter
from app.models.job import Job
from app.models.proposal import Proposal
from app.models.user import User
from app.services.outcome_report import (
    ReportRow,
    band,
    build_report,
    classify,
    days_to_first_reply,
    first_v2_letter_at,
    load_rows,
    render_text,
    summarise,
)

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)
SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _row(days_ago, stage="submitted", **kw):
    return ReportRow(sent_at=NOW - timedelta(days=days_ago), stage=stage, **kw)


def test_classify_pending_unknown_counted():
    assert classify(_row(3), NOW) == "pending"
    assert classify(_row(3, "viewed"), NOW) == "pending"
    assert classify(_row(20), NOW) == "counted"
    assert classify(_row(3, "replied"), NOW) == "counted"
    assert classify(_row(3, "declined"), NOW) == "counted"
    assert classify(_row(30, "unknown"), NOW) == "unknown"
    # an unknown raw status with a synced outcome or ledger stage is known
    assert classify(_row(30, "unknown", outcome="replied"), NOW) == "counted"
    assert classify(_row(30, "unknown", outcome="no_response"), NOW) == "unknown"
    assert classify(_row(30, "closed", ledger=[("submitted", "interview", NOW)]), NOW) == "counted"


def test_summarise_rates_and_small_denominators():
    rows = [_row(20) for _ in range(6)] + [
        _row(20, "viewed"), _row(20, "replied"), _row(20, "interview"), _row(20, "hired"),
        _row(2), _row(40, "unknown"),
    ]
    s = summarise(rows, NOW)
    assert (s["proposals"], s["sent"], s["pending"], s["unknown"]) == (12, 10, 1, 1)
    assert (s["viewed"], s["replied"], s["interview"], s["hired"]) == (4, 3, 2, 1)
    assert (s["viewed_rate"], s["replied_rate"], s["interview_rate"], s["hired_rate"]) == (40.0, 30.0, 20.0, 10.0)
    small = summarise([_row(20, "replied")] * 4, NOW)
    assert small["sent"] == 4 and small["replied_rate"] == "n<5" and small["hired_rate"] == "n<5"
    assert summarise([_row(20)] * 5, NOW)["replied_rate"] == 0.0


def test_reached_stage_survives_a_later_close():
    s = summarise([_row(30, "closed", ledger=[("submitted", "replied", NOW - timedelta(days=25))])] * 5, NOW)
    assert s["replied"] == 5 and s["hired"] == 0


def test_median_days_to_first_reply_uses_ledger_transitions_only():
    sent = NOW - timedelta(days=30)
    a = ReportRow(sent_at=sent, stage="interview", ledger=[
        ("submitted", "viewed", sent + timedelta(days=1)),
        ("viewed", "replied", sent + timedelta(days=2)),
        ("replied", "interview", sent + timedelta(days=5)),
    ])
    b = ReportRow(sent_at=sent, stage="replied", ledger=[("submitted", "replied", sent + timedelta(days=6))])
    created_replied = ReportRow(sent_at=sent, stage="replied", ledger=[(None, "replied", NOW)])
    assert days_to_first_reply(a) == 2.0
    assert days_to_first_reply(created_replied) is None
    s = summarise([a, b, created_replied], NOW)
    assert s["median_days_to_reply"] == 4.0 and s["reply_timings"] == 2
    assert summarise([_row(20)], NOW)["median_days_to_reply"] is None


def test_bands():
    assert [band(x) for x in (None, 0, 49.99, 50, 69.9, 70, 84.99, 85, 100)] == [
        "no score", "<50", "<50", "50-69", "50-69", "70-84", "70-84", "85+", "85+"]


def test_build_report_groups():
    rows = [
        _row(10, "replied", is_v2=True, match_score=90),     # v2, after since
        _row(40, "replied", is_v2=True),                     # v2 but before since: excluded
        _row(40, "submitted"),                               # baseline
        _row(28 + 91, "hired"),                              # older than the 90-day window
        _row(20, "submitted"),                               # non-v2 after since: in neither
    ]
    r = build_report(rows, SINCE, NOW)
    assert r["v2"]["overall"]["proposals"] == 1
    assert r["v2"]["by_match_score"]["85+"]["replied"] == 1
    assert r["baseline"]["overall"]["proposals"] == 1
    assert r["baseline"]["by_match_score"]["no score"]["proposals"] == 1
    text = render_text(r)
    assert "v2 engine" in text and "prior 90 days" in text and "n<5" in text


def _user():
    return User(email=f"report-{datetime.now().timestamp()}@example.com", hashed_password="x")


async def test_load_rows_links_v2_letters_like_outcome_sync(db_session):
    user = _user()
    db_session.add(user)
    await db_session.flush()
    jobs = {k: Job(user_id=user.id, upwork_url=f"https://www.upwork.com/jobs/~{k}", title=k,
                   description="d", skills_required=[], match_score=s)
            for k, s in (("v2", 88), ("legacy", 60), ("mixed", None))}
    db_session.add_all(jobs.values())
    await db_session.flush()
    first_v2 = datetime(2026, 10, 5, tzinfo=timezone.utc)
    db_session.add_all([
        CoverLetter(user_id=user.id, job_id=jobs["v2"].id, content="c", model_used="m",
                    prompt_version="v2", created_at=first_v2),
        CoverLetter(user_id=user.id, job_id=jobs["legacy"].id, content="c", model_used="m",
                    prompt_version="legacy"),
        # the sent (final_text) letter is legacy; a newer v2 draft for the same job is not it
        CoverLetter(user_id=user.id, job_id=jobs["mixed"].id, content="c", model_used="m",
                    prompt_version="legacy", final_text="sent"),
        CoverLetter(user_id=user.id, job_id=jobs["mixed"].id, content="c", model_used="m",
                    prompt_version="v2", created_at=first_v2 + timedelta(days=3)),
    ])
    sent = datetime(2026, 10, 10, tzinfo=timezone.utc)
    for key in jobs:
        db_session.add(Proposal(user_id=user.id, job_id=jobs[key].id, cover_letter_text="x",
                                status="responded", submitted_at=sent))
    db_session.add(Proposal(user_id=user.id, cover_letter_text="x", status="imported"))  # undated
    await db_session.commit()

    assert await first_v2_letter_at(db_session, user.id) == first_v2
    rows, undated = await load_rows(db_session, user.id)
    assert undated == 1
    by_score = {r.match_score: r for r in rows}
    assert by_score[88.0].is_v2 is True
    assert by_score[60.0].is_v2 is False
    assert by_score[None].is_v2 is False
    assert all(r.stage == "replied" and r.ledger for r in rows)


def test_script_parses_since_as_utc():
    script = Path(__file__).resolve().parents[2] / "scripts" / "outcome_report.py"
    spec = importlib.util.spec_from_file_location("outcome_report_script", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.parse_since("2026-10-20") == datetime(2026, 10, 20, tzinfo=timezone.utc)
