"""Regression: CoverLetter.model_used records the model that actually wrote the letter (phase 0)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services.job_analysis import AnalysisResult


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        match_score=70.0,
        skill_matches=[],
        missing_skills=[],
        strengths=[],
        concerns=[],
        deal_breaker_warnings=[],
        relevant_memories=[],
        recommendation="Good match - consider applying",
    )


JOB_DATA = {
    "upwork_url": "https://www.upwork.com/jobs/~01model0used",
    "title": "Build a FastAPI backend",
    "description": "Need an async FastAPI service with Postgres.",
    "skills_required": ["Python", "FastAPI"],
}


@pytest.mark.asyncio
async def test_generate_and_regenerate_record_cover_letter_model(
    client: AsyncClient, auth_headers_with_profile: dict
):
    assert settings.legacy_cover_letter_model != settings.default_model

    with patch("app.api.v1.jobs.generate_embedding", AsyncMock(return_value=[0.1] * 1536)), \
         patch("app.api.v1.jobs.run_full_analysis", AsyncMock(return_value=_analysis())), \
         patch("app.api.v1.jobs.find_relevant_proposals", AsyncMock(return_value=[])), \
         patch("app.api.v1.jobs.generate_cover_letter", AsyncMock(return_value="First draft body.")), \
         patch("app.api.v1.jobs.regenerate_cover_letter", AsyncMock(return_value="Second draft body.")):
        r = await client.post(
            "/api/v1/jobs/cover-letters/generate",
            headers=auth_headers_with_profile,
            json={"job_data": JOB_DATA},
        )
        assert r.status_code == 200, r.text
        assert r.json()["model_used"] == settings.legacy_cover_letter_model

        r2 = await client.post(
            f"/api/v1/jobs/cover-letters/{r.json()['id']}/regenerate",
            headers=auth_headers_with_profile,
            json={"feedback": "Shorter, lead with the Postgres work."},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["model_used"] == settings.legacy_cover_letter_model
