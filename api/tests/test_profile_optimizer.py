"""Tests for profile_optimizer service."""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.profile import (
    May2026Item,
    ProfileDimension,
    ProfileOptimizeResponse,
    ProfileRecommendation,
)
from app.services.profile_optimizer import _build_optimization_prompt, optimize_profile


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_profile(**kwargs):
    """Build a minimal mock UserProfile."""
    p = MagicMock()
    p.professional_title = kwargs.get("professional_title", "Senior Developer")
    p.bio = kwargs.get("bio", "Experienced developer with 10 years building APIs.")
    p.hourly_rate_preferred = kwargs.get("hourly_rate_preferred", 125)
    p.hourly_rate_min = kwargs.get("hourly_rate_min", 100)
    p.hours_per_week_available = kwargs.get("hours_per_week_available", 20)
    p.currently_accepting_work = kwargs.get("currently_accepting_work", True)
    p.skills = kwargs.get("skills", [{"name": "Python"}, {"name": "FastAPI"}])
    p.proposal_anchors = kwargs.get("proposal_anchors", {})
    p.portfolio_links = kwargs.get("portfolio_links", [])
    return p


_MINIMAL_RESPONSE = {
    "overall_score": 55,
    "dimensions": [
        {
            "name": "Title",
            "score": 70,
            "status": "warning",
            "summary": "Title is reasonable.",
            "detail": "Could be more keyword-focused.",
        }
    ],
    "recommendations": [
        {
            "priority": "medium",
            "dimension": "Title",
            "title": "Improve title",
            "problem": "Not keyword-rich.",
            "action": "Use primary keyword first.",
        }
    ],
    "suggested_title": "Python Developer | FastAPI | REST APIs",
    "suggested_overview_hook": "I help SaaS founders ship reliable Python APIs fast.",
    "suggested_skills": ["Python", "FastAPI", "PostgreSQL"],
    "may_2026_checklist": [
        {
            "item": "Merge specialized profile content into main",
            "done": False,
            "note": "Not done yet.",
        }
    ],
}


def _mock_anthropic_response(data: dict):
    """Return a mock Anthropic client whose messages.create returns data as JSON."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(data))]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)
    return mock_client


# ── Prompt construction ───────────────────────────────────────────────────────

def test_prompt_includes_title():
    profile = _make_profile(professional_title="AI Engineer")
    prompt = _build_optimization_prompt(profile)
    assert "AI Engineer" in prompt


def test_prompt_includes_bio_length():
    bio = "x" * 500
    profile = _make_profile(bio=bio)
    prompt = _build_optimization_prompt(profile)
    assert "500" in prompt


def test_prompt_includes_skill_count():
    profile = _make_profile(skills=[{"name": "Python"}, {"name": "Go"}, {"name": "Rust"}])
    prompt = _build_optimization_prompt(profile)
    assert "3" in prompt


def test_prompt_handles_empty_profile():
    """Prompt should not raise when all optional fields are None/empty."""
    profile = _make_profile(
        professional_title=None,
        bio=None,
        hourly_rate_preferred=None,
        hourly_rate_min=None,
        hours_per_week_available=None,
        skills=[],
        proposal_anchors=None,
        portfolio_links=None,
    )
    prompt = _build_optimization_prompt(profile)
    assert "FREELANCER PROFILE DATA" in prompt


def test_prompt_includes_portfolio_count():
    profile = _make_profile(portfolio_links=["https://a.com", "https://b.com"])
    prompt = _build_optimization_prompt(profile)
    assert "Portfolio Links Count: 2" in prompt


# ── optimize_profile function ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_optimize_returns_response_on_success():
    profile = _make_profile()
    mock_client = _mock_anthropic_response(_MINIMAL_RESPONSE)

    with patch("app.services.profile_optimizer._get_anthropic_client", return_value=mock_client):
        result = await optimize_profile(profile)

    assert isinstance(result, ProfileOptimizeResponse)
    assert result.overall_score == 55
    assert len(result.dimensions) == 1
    assert result.dimensions[0].name == "Title"
    assert result.cached is False


@pytest.mark.asyncio
async def test_optimize_strips_markdown_code_fences():
    """Model sometimes wraps JSON in triple backticks — should be stripped."""
    profile = _make_profile()
    raw = f"```json\n{json.dumps(_MINIMAL_RESPONSE)}\n```"
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=raw)]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    with patch("app.services.profile_optimizer._get_anthropic_client", return_value=mock_client):
        result = await optimize_profile(profile)

    assert result.overall_score == 55


@pytest.mark.asyncio
async def test_optimize_raises_on_invalid_json():
    """json.JSONDecodeError should propagate (triggering tenacity retry then fail)."""
    profile = _make_profile()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not valid json at all")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    with patch("app.services.profile_optimizer._get_anthropic_client", return_value=mock_client):
        with pytest.raises(Exception):
            await optimize_profile.__wrapped__(profile)  # bypass tenacity retry


@pytest.mark.asyncio
async def test_optimize_returns_empty_collections_on_missing_keys():
    """Missing optional keys default gracefully."""
    minimal = {"overall_score": 40, "dimensions": [], "recommendations": [],
                "may_2026_checklist": []}
    profile = _make_profile()
    mock_client = _mock_anthropic_response(minimal)

    with patch("app.services.profile_optimizer._get_anthropic_client", return_value=mock_client):
        result = await optimize_profile(profile)

    assert result.overall_score == 40
    assert result.dimensions == []
    assert result.recommendations == []
    assert result.suggested_title is None
    assert result.suggested_skills is None


@pytest.mark.asyncio
async def test_optimize_empty_profile_does_not_raise():
    """All-None profile fields should produce a result without an exception."""
    profile = _make_profile(
        professional_title=None,
        bio=None,
        hourly_rate_preferred=None,
        hourly_rate_min=None,
        hours_per_week_available=None,
        skills=[],
        proposal_anchors=None,
        portfolio_links=None,
    )
    mock_client = _mock_anthropic_response(_MINIMAL_RESPONSE)

    with patch("app.services.profile_optimizer._get_anthropic_client", return_value=mock_client):
        result = await optimize_profile(profile)

    assert isinstance(result, ProfileOptimizeResponse)
