"""Tests for job analysis service functions (pure logic, no DB needed)."""
import pytest
from unittest.mock import MagicMock

from app.services.job_analysis import (
    normalize_skill,
    skills_match,
    find_related_skill,
    analyze_skill_match,
    check_deal_breakers,
    generate_strengths_and_concerns,
    calculate_match_score,
    generate_recommendation,
)
from app.schemas.job import SkillMatch


# --- normalize_skill ---

def test_normalize_skill_strips_and_lowercases():
    assert normalize_skill("  Python  ") == "python"
    assert normalize_skill("React.js") == "react.js"


# --- skills_match ---

def test_skills_match_exact():
    assert skills_match("Python", "python") is True
    assert skills_match("React", "react") is True


def test_skills_match_synonym():
    assert skills_match("react", "reactjs") is True
    assert skills_match("node", "nodejs") is True
    assert skills_match("typescript", "ts") is True
    assert skills_match("postgresql", "postgres") is True


def test_skills_match_no_match():
    assert skills_match("python", "java") is False
    assert skills_match("react", "angular") is False


# --- find_related_skill ---

def test_find_related_skill_exact():
    user_skills = [{"name": "Python", "level": "expert"}]
    result = find_related_skill("python", user_skills)
    assert result is not None
    skill, match_type = result
    assert match_type == "exact"


def test_find_related_skill_synonym():
    user_skills = [{"name": "React", "level": "intermediate"}]
    result = find_related_skill("reactjs", user_skills)
    assert result is not None
    _, match_type = result
    assert match_type == "exact"  # Synonym counts as exact in this impl


def test_find_related_skill_partial():
    user_skills = [{"name": "Machine Learning", "level": "intermediate"}]
    result = find_related_skill("machine", user_skills)
    assert result is not None
    _, match_type = result
    assert match_type == "related"


def test_find_related_skill_no_match():
    user_skills = [{"name": "Python", "level": "expert"}]
    result = find_related_skill("Kubernetes", user_skills)
    assert result is None


# --- analyze_skill_match ---

@pytest.mark.asyncio
async def test_analyze_skill_match_full_match():
    profile = MagicMock()
    profile.skills = [
        {"name": "Python", "level": "expert"},
        {"name": "React", "level": "intermediate"},
    ]
    matches, missing = await analyze_skill_match(["python", "react"], profile)
    assert len(matches) == 2
    assert len(missing) == 0


@pytest.mark.asyncio
async def test_analyze_skill_match_partial():
    profile = MagicMock()
    profile.skills = [{"name": "Python", "level": "expert"}]
    matches, missing = await analyze_skill_match(["python", "java", "go"], profile)
    assert len(matches) == 1
    assert set(missing) == {"java", "go"}


@pytest.mark.asyncio
async def test_analyze_skill_match_no_user_skills():
    profile = MagicMock()
    profile.skills = None
    matches, missing = await analyze_skill_match(["python"], profile)
    assert len(matches) == 0
    assert missing == ["python"]


@pytest.mark.asyncio
async def test_analyze_skill_match_empty_job_skills():
    profile = MagicMock()
    profile.skills = [{"name": "Python", "level": "expert"}]
    matches, missing = await analyze_skill_match([], profile)
    assert len(matches) == 0
    assert len(missing) == 0


# --- check_deal_breakers ---

def _make_profile(**kwargs):
    profile = MagicMock()
    profile.avoid_keywords = kwargs.get("avoid_keywords", None)
    profile.minimum_budget = kwargs.get("minimum_budget", None)
    profile.minimum_hourly_rate = kwargs.get("minimum_hourly_rate", None)
    profile.red_flag_patterns = kwargs.get("red_flag_patterns", None)
    return profile


def test_deal_breakers_avoided_keyword():
    profile = _make_profile(avoid_keywords=["crypto", "blockchain"])
    warnings = check_deal_breakers(
        "We need a crypto trading bot", [], None, None, None, profile
    )
    assert any("crypto" in w for w in warnings)


def test_deal_breakers_minimum_budget():
    profile = _make_profile(minimum_budget=500)
    warnings = check_deal_breakers("Build a website", [], None, 200.0, None, profile)
    assert any("below your minimum" in w for w in warnings)


def test_deal_breakers_minimum_hourly_rate():
    profile = _make_profile(minimum_hourly_rate=50)
    warnings = check_deal_breakers(
        "Build a website", [], "$25/hr", None, None, profile
    )
    assert any("below your minimum" in w for w in warnings)


def test_deal_breakers_red_flag():
    profile = _make_profile(red_flag_patterns=["unpaid trial"])
    warnings = check_deal_breakers(
        "We require an unpaid trial period", [], None, None, None, profile
    )
    assert any("Red flag" in w for w in warnings)


def test_deal_breakers_client_zero_hire_rate():
    profile = _make_profile()
    warnings = check_deal_breakers(
        "Build something", [], None, None, {"hire_rate": "0%"}, profile
    )
    assert any("0% hire rate" in w for w in warnings)


def test_deal_breakers_no_issues():
    profile = _make_profile(avoid_keywords=["crypto"], minimum_budget=100)
    warnings = check_deal_breakers(
        "Build a React dashboard", ["React"], "$50/hr", 500.0, None, profile
    )
    assert len(warnings) == 0


# --- calculate_match_score ---

def test_calculate_match_score_perfect():
    matches = [
        SkillMatch(skill="Python", match_type="exact", user_level="expert", relevance_score=1.0),
        SkillMatch(skill="React", match_type="exact", user_level="expert", relevance_score=1.0),
    ]
    memories = [{"similarity": 0.8}, {"similarity": 0.7}]
    profile = MagicMock()
    profile.bio = "Experienced developer"
    profile.skills = [{"name": "Python"}]
    profile.work_history = [{"title": "Dev"}]
    profile.unique_strengths = ["Fast learner"]

    score = calculate_match_score(matches, [], memories, [], profile)
    assert score >= 70  # Should be a high score


def test_calculate_match_score_with_deal_breakers():
    matches = [
        SkillMatch(skill="Python", match_type="exact", user_level="expert", relevance_score=1.0),
    ]
    profile = MagicMock()
    profile.bio = "Dev"
    profile.skills = [{"name": "Python"}]
    profile.work_history = None
    profile.unique_strengths = None

    score_without = calculate_match_score(matches, [], [], [], profile)
    score_with = calculate_match_score(matches, [], [], ["Budget too low"], profile)
    assert score_with < score_without


def test_calculate_match_score_no_skills():
    profile = MagicMock()
    profile.bio = None
    profile.skills = None
    profile.work_history = None
    profile.unique_strengths = None

    score = calculate_match_score([], [], [], [], profile)
    assert 0 <= score <= 100


# --- generate_recommendation ---

def test_recommendation_excellent():
    rec = generate_recommendation(85, [], [])
    assert "excellent" in rec.lower() or "highly recommended" in rec.lower()


def test_recommendation_good():
    rec = generate_recommendation(70, [], [])
    assert "good" in rec.lower()


def test_recommendation_moderate():
    rec = generate_recommendation(55, [], [])
    assert "moderate" in rec.lower()


def test_recommendation_low():
    rec = generate_recommendation(30, [], [])
    assert "lower" in rec.lower()


def test_recommendation_deal_breakers():
    rec = generate_recommendation(85, ["Budget issue"], [])
    assert "issue" in rec.lower() or "review" in rec.lower()


# --- generate_strengths_and_concerns ---

def test_strengths_expert_skills():
    matches = [
        SkillMatch(skill="Python", match_type="exact", user_level="expert", relevance_score=1.0),
        SkillMatch(skill="React", match_type="exact", user_level="expert", relevance_score=1.0),
    ]
    profile = MagicMock()
    profile.unique_strengths = None
    profile.hourly_rate_preferred = None

    strengths, concerns = generate_strengths_and_concerns(
        matches, [], [], profile, None
    )
    assert any("expert" in s.lower() for s in strengths)


def test_concerns_missing_skills():
    profile = MagicMock()
    profile.unique_strengths = None
    profile.hourly_rate_preferred = None

    strengths, concerns = generate_strengths_and_concerns(
        [], ["Java", "Go"], [], profile, None
    )
    assert any("missing" in c.lower() for c in concerns)
