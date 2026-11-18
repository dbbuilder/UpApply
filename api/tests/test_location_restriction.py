"""Upwork's job-page restriction line ("Only freelancers located in the U.S. may apply.") is not
in the description; POST /jobs/analyze adds it to the text the must-have check reads."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.job_analysis import AnalysisResult


def _analysis():
    return AnalysisResult(match_score=70.0, skill_matches=[], missing_skills=[], strengths=[], concerns=[],
                          deal_breaker_warnings=[], relevant_memories=[], recommendation="Apply")


@pytest.mark.asyncio
async def test_the_restriction_line_reaches_the_analysis(client, auth_headers_with_profile):
    run = AsyncMock(return_value=_analysis())
    body = {"title": "CRM in Floot", "description": "Finish our CRM.",
            "location_restriction": "Only freelancers located in the U.S. may apply."}
    with patch("app.api.v1.jobs.run_full_analysis", run):
        resp = await client.post("/api/v1/jobs/analyze", json=body, headers=auth_headers_with_profile)
    assert resp.status_code == 200
    assert run.await_args.kwargs["job_description"] == "Finish our CRM."
    assert run.await_args.kwargs["location_restriction"] == "Only freelancers located in the U.S. may apply."


@pytest.mark.asyncio
async def test_no_restriction_leaves_the_description_alone(client, auth_headers_with_profile):
    run = AsyncMock(return_value=_analysis())
    with patch("app.api.v1.jobs.run_full_analysis", run):
        await client.post("/api/v1/jobs/analyze", json={"title": "t", "description": "d", "location_restriction": "  "},
                          headers=auth_headers_with_profile)
    assert run.await_args.kwargs["job_description"] == "d"
    assert run.await_args.kwargs["location_restriction"] is None


@pytest.mark.asyncio
async def test_an_oversized_restriction_is_rejected(client, auth_headers_with_profile):
    resp = await client.post("/api/v1/jobs/analyze", headers=auth_headers_with_profile,
                             json={"title": "t", "description": "d", "location_restriction": "x" * 201})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_the_rule_reaches_the_check_even_past_the_description_cut():
    from types import SimpleNamespace
    from app.services import job_requirements as jr

    rule = "Only freelancers located in the U.S. may apply."
    long_post = "We need a CRM finished. " * 400  # far past MAX_DESCRIPTION_CHARS
    reply = {"must_haves": [{"requirement": "Located in the U.S.", "quote": rule, "kind": "location",
                             "status": "unmet", "why": "Profile location is Canada"}]}
    call = AsyncMock(return_value=reply)
    profile = SimpleNamespace(freelancer_location="Canada", timezone=None, certifications=[], skills=[],
                              preferred_project_types=[], career_goals=None)
    with patch.object(jr, "structured_call", call), patch.object(jr.settings, "anthropic_api_key", "sk-test"):
        check = await jr.check_requirements(title="CRM", description=long_post, profile=profile, facts=[],
                                            location_restriction=rule)
    assert "Upwork rule for this job: Only freelancers located in the U.S. may apply." in call.await_args.kwargs["user"]
    assert [m.quote for m in check.unmet] == [rule]  # a quote from the rule line passes the verbatim check
