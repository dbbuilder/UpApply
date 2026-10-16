"""Regression: POST /screening-answers/generate with job context (phase 0)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


def _mock_openai(answer: str = "Built three of these for fintech clients."):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = answer
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_generate_with_job_context_includes_context_in_prompt(
    client: AsyncClient, auth_headers_with_profile: dict
):
    openai_client = _mock_openai()
    with patch(
        "app.api.v1.screening_answers.generate_embedding",
        AsyncMock(return_value=[0.1] * 1536),
    ), patch(
        "app.api.v1.screening_answers.get_openai_client",
        return_value=openai_client,
    ):
        r = await client.post(
            "/api/v1/screening-answers/generate",
            headers=auth_headers_with_profile,
            json={
                "question": "Describe your recent experience with similar projects",
                "job_title": "FastAPI pgvector search build",
                "job_description": "We need semantic search over 2M support tickets.",
                "job_skills": ["Python", "PostgreSQL", "pgvector"],
            },
        )

    assert r.status_code == 200
    assert r.json()["answer"] == "Built three of these for fintech clients."
    user_prompt = openai_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "Job: FastAPI pgvector search build" in user_prompt
    assert "Required skills: Python, PostgreSQL, pgvector" in user_prompt
    assert "Description excerpt: We need semantic search over 2M support tickets." in user_prompt


@pytest.mark.asyncio
async def test_generate_without_job_context_still_works(
    client: AsyncClient, auth_headers_with_profile: dict
):
    openai_client = _mock_openai("Available 30 hrs/week.")
    with patch(
        "app.api.v1.screening_answers.generate_embedding",
        AsyncMock(return_value=[0.1] * 1536),
    ), patch(
        "app.api.v1.screening_answers.get_openai_client",
        return_value=openai_client,
    ):
        r = await client.post(
            "/api/v1/screening-answers/generate",
            headers=auth_headers_with_profile,
            json={"question": "What is your availability?"},
        )

    assert r.status_code == 200
    user_prompt = openai_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "JOB CONTEXT" not in user_prompt
