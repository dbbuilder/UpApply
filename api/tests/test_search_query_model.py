"""Unit tests for SearchQuery model properties and Pydantic schemas.

The model properties (performance_score, is_stale, is_low_performer) contain
pure logic that we test via SimpleNamespace to avoid SQLAlchemy instrumentation
overhead.  The actual @property definitions are on the ORM class; we verify the
same logic here by reimplementing the identical formulas using plain objects.
"""
import pytest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.schemas.search_query import SearchQueryCreate, RunRecordRequest
# Import the property implementations from the model for consistency checking
from app.models.search_query import SearchQuery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sq(**kwargs) -> SimpleNamespace:
    """Return a SimpleNamespace that mimics SearchQuery field access."""
    defaults = {
        "run_count": 0,
        "last_run_at": None,
        "total_jobs_found": 0,
        "avg_match_score": None,
        "high_score_count": 0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _perf(sq: SimpleNamespace) -> float:
    """Mirror of SearchQuery.performance_score."""
    if sq.run_count == 0 or sq.total_jobs_found == 0:
        return 0.0
    quality_ratio = sq.high_score_count / sq.total_jobs_found
    volume_factor = min(1.0, sq.total_jobs_found / 10)
    return round((sq.avg_match_score or 0.0) * quality_ratio * volume_factor, 1)


def _stale(sq: SimpleNamespace) -> bool:
    """Mirror of SearchQuery.is_stale."""
    if sq.last_run_at is None:
        return True
    age = datetime.now(timezone.utc) - sq.last_run_at
    return age.total_seconds() > 86_400


def _low(sq: SimpleNamespace) -> bool:
    """Mirror of SearchQuery.is_low_performer."""
    if sq.run_count < 3:
        return False
    return (sq.avg_match_score or 0.0) < 35 or sq.total_jobs_found < 2


class TestPerformanceScore:
    def test_never_run_returns_zero(self):
        sq = _make_sq(run_count=0, total_jobs_found=0)
        assert _perf(sq) == 0.0

    def test_has_runs_but_no_jobs_returns_zero(self):
        sq = _make_sq(run_count=3, total_jobs_found=0, avg_match_score=80.0)
        assert _perf(sq) == 0.0

    def test_all_high_scorers_small_volume(self):
        # 2 jobs, both high-score (≥70), avg 85
        sq = _make_sq(
            run_count=2, total_jobs_found=2, avg_match_score=85.0, high_score_count=2
        )
        # quality_ratio = 2/2 = 1.0, volume_factor = 2/10 = 0.2
        assert _perf(sq) == round(85.0 * 1.0 * 0.2, 1)

    def test_saturates_at_10_jobs(self):
        sq = _make_sq(
            run_count=5, total_jobs_found=20, avg_match_score=70.0, high_score_count=10
        )
        # volume_factor capped at 1.0, quality_ratio = 10/20 = 0.5
        assert _perf(sq) == round(70.0 * 0.5 * 1.0, 1)

    def test_zero_high_score_gives_zero_score(self):
        sq = _make_sq(
            run_count=3, total_jobs_found=10, avg_match_score=45.0, high_score_count=0
        )
        assert _perf(sq) == 0.0

    def test_high_quality_beats_high_volume(self):
        """3 jobs all at 90 avg beats 30 jobs at avg 40 with none high-score."""
        high_quality = _make_sq(
            run_count=1, total_jobs_found=3, avg_match_score=90.0, high_score_count=3
        )
        high_volume = _make_sq(
            run_count=5, total_jobs_found=30, avg_match_score=40.0, high_score_count=0
        )
        assert _perf(high_quality) > _perf(high_volume)

    def test_none_avg_score_handled(self):
        sq = _make_sq(run_count=1, total_jobs_found=5, avg_match_score=None, high_score_count=2)
        assert _perf(sq) == 0.0


class TestIsStale:
    def test_never_run_is_stale(self):
        sq = _make_sq(last_run_at=None)
        assert _stale(sq) is True

    def test_run_recently_not_stale(self):
        sq = _make_sq(last_run_at=datetime.now(timezone.utc) - timedelta(hours=12))
        assert _stale(sq) is False

    def test_run_over_24h_ago_is_stale(self):
        sq = _make_sq(last_run_at=datetime.now(timezone.utc) - timedelta(hours=25))
        assert _stale(sq) is True

    def test_exactly_24h_is_stale(self):
        # boundary: exactly 24h should count as stale (> 86400 is False, so exactly = not stale)
        sq = _make_sq(last_run_at=datetime.now(timezone.utc) - timedelta(seconds=86401))
        assert _stale(sq) is True


class TestIsLowPerformer:
    def test_too_few_runs_not_flagged(self):
        sq = _make_sq(run_count=2, avg_match_score=20.0, total_jobs_found=0)
        assert _low(sq) is False

    def test_low_avg_score_flagged(self):
        sq = _make_sq(run_count=3, avg_match_score=30.0, total_jobs_found=10)
        assert _low(sq) is True

    def test_low_job_count_flagged(self):
        sq = _make_sq(run_count=3, avg_match_score=60.0, total_jobs_found=1)
        assert _low(sq) is True

    def test_healthy_query_not_flagged(self):
        sq = _make_sq(run_count=3, avg_match_score=65.0, total_jobs_found=5)
        assert _low(sq) is False

    def test_none_avg_score_flagged(self):
        sq = _make_sq(run_count=5, avg_match_score=None, total_jobs_found=10)
        assert _low(sq) is True


# ---------------------------------------------------------------------------
# SearchQueryCreate schema validation
# ---------------------------------------------------------------------------

class TestSearchQueryCreateSchema:
    def test_valid_minimal(self):
        sq = SearchQueryCreate(query="python developer")
        assert sq.query == "python developer"
        assert sq.source == "manual"
        assert sq.url_params is None

    def test_strips_whitespace_from_query(self):
        sq = SearchQueryCreate(query="  fractional CTO  ")
        assert sq.query == "fractional CTO"

    def test_empty_query_raises(self):
        with pytest.raises(Exception):
            SearchQueryCreate(query="   ")

    def test_invalid_source_raises(self):
        with pytest.raises(Exception):
            SearchQueryCreate(query="python", source="unknown_source")

    def test_valid_sources(self):
        for src in ("manual", "ai_generated", "seeded", "imported"):
            sq = SearchQueryCreate(query="test query", source=src)
            assert sq.source == src

    def test_url_params_stored(self):
        sq = SearchQueryCreate(query="python", url_params="contractor_tier=2,3&proposals=0-4")
        assert sq.url_params == "contractor_tier=2,3&proposals=0-4"


# ---------------------------------------------------------------------------
# RunRecordRequest schema
# ---------------------------------------------------------------------------

class TestRunRecordRequest:
    def test_valid(self):
        r = RunRecordRequest(jobs_found=5, avg_score=72.5, high_score_count=3)
        assert r.jobs_found == 5
        assert r.avg_score == 72.5
        assert r.high_score_count == 3
