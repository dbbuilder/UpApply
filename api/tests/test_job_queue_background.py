"""Regression: job-queue background tasks call run_full_analysis with its real signature (phase 0)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1 import job_queue
from app.services.job_analysis import AnalysisResult


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        match_score=82.0,
        skill_matches=[],
        missing_skills=["Rust"],
        strengths=["Deep PostgreSQL background"],
        concerns=[],
        deal_breaker_warnings=[],
        relevant_memories=[],
        recommendation="Excellent match - highly recommended to apply",
    )


def _item():
    return SimpleNamespace(
        id="item-1",
        title="Postgres tuning for SaaS",
        description="Slow queries on a 400GB database.",
        skills=["PostgreSQL", "Python"],
        budget_amount="$2,000",
        client_info={"location": "United States"},
        draft_cover_letter=None,
        draft_status="generating",
        draft_generated_at=None,
        ai_score=None,
        ai_reasoning=None,
    )


def _session_maker(item):
    result = MagicMock()
    result.scalar_one_or_none.return_value = item
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    maker = MagicMock()
    maker.return_value.__aenter__.return_value = db
    maker.return_value.__aexit__.return_value = False
    return maker, db


def _assert_called_with_real_signature(mock_rfa, db, profile, item):
    mock_rfa.assert_awaited_once()
    kwargs = mock_rfa.call_args.kwargs
    assert kwargs["db"] is db
    assert kwargs["user_id"] == "user-1"
    assert kwargs["profile"] is profile
    assert kwargs["job_description"] == item.description
    assert kwargs["job_skills"] == item.skills
    assert kwargs["job_title"] == item.title
    assert kwargs["budget_amount"] == item.budget_amount
    assert kwargs["client_info"] == item.client_info


@pytest.mark.asyncio
async def test_generate_draft_background_produces_ready_draft():
    item = _item()
    profile = MagicMock(generation_v2=False)
    maker, db = _session_maker(item)

    with patch("app.core.database.async_session_maker", maker), \
         patch.object(job_queue, "_get_user_profile", AsyncMock(return_value=profile)), \
         patch.object(job_queue, "_record_outcome", AsyncMock()), \
         patch.object(job_queue, "record_proposal_drafted", AsyncMock()), \
         patch("app.services.job_analysis.run_full_analysis", autospec=True) as mock_rfa, \
         patch("app.services.job_analysis.find_relevant_proposals", AsyncMock(return_value=[])), \
         patch("app.services.cover_letter.generate_cover_letter", AsyncMock(return_value="Draft body")):
        mock_rfa.return_value = _analysis()
        await job_queue._generate_draft_background(item_id="item-1", user_id="user-1")

    _assert_called_with_real_signature(mock_rfa, db, profile, item)
    assert item.draft_status == "ready"
    assert item.draft_cover_letter == "Draft body"


@pytest.mark.asyncio
async def test_score_pre_filtered_background_sets_score():
    item = _item()
    profile = MagicMock()
    maker, db = _session_maker(item)

    with patch("app.core.database.async_session_maker", maker), \
         patch.object(job_queue, "_get_user_profile", AsyncMock(return_value=profile)), \
         patch("app.services.job_analysis.run_full_analysis", autospec=True) as mock_rfa:
        mock_rfa.return_value = _analysis()
        await job_queue._score_pre_filtered_background(item_id="item-1", user_id="user-1")

    _assert_called_with_real_signature(mock_rfa, db, profile, item)
    assert item.ai_score == 82.0
    assert "Missing: Rust." in item.ai_reasoning
