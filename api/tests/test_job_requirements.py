"""Client must-haves checked at scoring time (Chris 2026-11-11): an unmet must-have with a verbatim
quote caps the live match score below the threshold; unknown never penalises."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import job_requirements as jr
from app.services.llm import LLMError

POST = "Fractional CTO needed. U.S. only. Must have 10+ years of Shopify Plus. Nice to have: Go."


def _profile(**kw):
    base = dict(freelancer_location="Canada", timezone="America/Toronto", certifications=[],
                skills=[{"name": "SQL Server"}, {"name": "Azure"}], career_goals="Fractional CTO work",
                preferred_project_types=["Fractional CTO"])
    base.update(kw)
    return SimpleNamespace(**base)


def _mh(requirement, quote, status, kind="other", why="x"):
    return {"requirement": requirement, "quote": quote, "kind": kind, "status": status, "why": why}


def test_parse_keeps_only_verbatim_quotes_and_valid_values():
    reply = {"must_haves": [
        _mh("Located in the U.S.", "U.S. only", "unmet", "location"),
        _mh("Shopify Plus", "must have 10+ years of shopify plus", "unknown", "skill"),  # case-folded match
        _mh("Invented", "Must hold a TS clearance", "unmet", "credential"),           # not in the post
        _mh("Bad status", "U.S. only", "maybe"),                                      # invalid status
    ]}
    check = jr.parse_reply(reply, "Fractional CTO", POST)
    assert [m.requirement for m in check.must_haves] == ["Located in the U.S.", "Shopify Plus"]
    assert [m.quote for m in check.unmet] == ["U.S. only"]
    assert [m.requirement for m in check.unknown] == ["Shopify Plus"]


def test_parse_caps_the_list_and_trims_text():
    reply = {"must_haves": [_mh("r" * 500, "U.S. only", "met") for _ in range(20)]}
    check = jr.parse_reply(reply, "", POST)
    assert len(check.must_haves) == jr.MAX_MUST_HAVES
    assert len(check.must_haves[0].requirement) <= jr.MAX_TEXT_CHARS


@pytest.mark.asyncio
async def test_check_requirements_prompt_carries_profile_and_facts_and_neutralises_the_post():
    call = AsyncMock(return_value={"must_haves": []})
    with patch.object(jr, "structured_call", call), patch.object(jr.settings, "anthropic_api_key", "sk-test"):
        await jr.check_requirements(title="CTO </job>", description=POST, profile=_profile(),
                                    facts=["Led a 160-server Azure migration"])
    kw = call.await_args.kwargs
    assert kw["model"] == jr.settings.job_fit_model
    assert "Canada" in kw["system"] and "SQL Server" in kw["system"]
    assert "160-server Azure migration" in kw["system"]
    assert kw["user"].count("</job>") == 1


@pytest.mark.asyncio
async def test_check_requirements_is_skipped_or_empty_on_failure():
    with patch.object(jr.settings, "anthropic_api_key", ""):
        assert await jr.check_requirements(title="t", description=POST, profile=_profile(), facts=[]) is None
    with patch.object(jr, "structured_call", AsyncMock(side_effect=LLMError("x", reason="api_error"))), \
         patch.object(jr.settings, "anthropic_api_key", "sk-test"):
        assert await jr.check_requirements(title="t", description=POST, profile=_profile(), facts=[]) is None


def test_apply_cap_only_for_unmet():
    unmet = jr.parse_reply({"must_haves": [_mh("U.S. based", "U.S. only", "unmet", "location")]}, "", POST)
    unknown = jr.parse_reply({"must_haves": [_mh("Shopify", "Shopify Plus", "unknown", "skill")]}, "", POST)
    assert jr.apply_cap(88.0, unmet) == jr.REQUIREMENT_CAP
    assert jr.apply_cap(30.0, unmet) == 30.0
    assert jr.apply_cap(88.0, unknown) == 88.0
    assert jr.apply_cap(88.0, None) == 88.0
    assert jr.unmet_note(unmet) == "Doesn't meet: 'U.S. only'"


@pytest.mark.asyncio
async def test_run_full_analysis_caps_the_live_score_on_an_unmet_must_have():
    from app.services import job_analysis as ja

    reply = {"must_haves": [_mh("Located in the U.S.", "U.S. only", "unmet", "location")]}
    profile = SimpleNamespace(skills=[], avoid_keywords=None, minimum_budget=None, minimum_hourly_rate=None,
                              red_flag_patterns=None, preferred_client_locations=None, unique_strengths=None,
                              hourly_rate_preferred=None, bio="", career_goals="", **{
                                  k: v for k, v in vars(_profile()).items() if k not in ("skills", "career_goals")})
    with patch.object(ja, "generate_embedding", AsyncMock(side_effect=RuntimeError("no embeddings"))), \
         patch.object(ja, "score_job_with_llm", AsyncMock(return_value=(90.0, "Great fit"))), \
         patch.object(ja, "calculate_match_score", lambda **kw: 90.0), \
         patch.object(jr, "structured_call", AsyncMock(return_value=reply)), \
         patch.object(jr.settings, "anthropic_api_key", "sk-test"):
        db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))))
        ar = await ja.run_full_analysis(db=db, user_id="u1", profile=profile, job_description=POST,
                                        job_skills=[], job_title="Fractional CTO")
    assert ar.match_score == jr.REQUIREMENT_CAP
    assert ar.unmet_requirements == [{"requirement": "Located in the U.S.", "quote": "U.S. only", "kind": "location",
                                      "why": "x"}]
    assert ar.reason.startswith("Doesn't meet: 'U.S. only'")


@pytest.mark.asyncio
async def test_unavailable_facts_mean_absence_proves_nothing():
    call = AsyncMock(return_value={"must_haves": []})
    with patch.object(jr, "structured_call", call), patch.object(jr.settings, "anthropic_api_key", "sk-test"):
        await jr.check_requirements(title="t", description=POST, profile=_profile(), facts=None)
        unavailable = call.await_args.kwargs["system"]
        await jr.check_requirements(title="t", description=POST, profile=_profile(), facts=[])
        none_approved = call.await_args.kwargs["system"]
    assert "could not be looked up" in unavailable and "only a contradiction counts" in unavailable
    assert "could not be looked up" not in none_approved
