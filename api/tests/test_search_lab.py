"""Unit tests for app.services.search_lab (no DB, no real OpenAI)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search_lab import (
    tokenize_query,
    job_matches_query,
    TargetJob,
)


# ---------------------------------------------------------------------------
# tokenize_query
# ---------------------------------------------------------------------------

def test_tokenize_strips_stop_words():
    tokens = tokenize_query("a senior developer for the web")
    assert "senior" in tokens
    assert "developer" in tokens
    assert "web" in tokens
    # stop words removed
    assert "a" not in tokens
    assert "the" not in tokens
    assert "for" not in tokens


def test_tokenize_lowercases():
    tokens = tokenize_query("Python FastAPI React")
    assert tokens == ["python", "fastapi", "react"]


def test_tokenize_strips_punctuation():
    tokens = tokenize_query('"python" (react) or fastapi')
    assert "python" in tokens
    assert "react" in tokens
    assert "fastapi" in tokens


def test_tokenize_empty_string():
    assert tokenize_query("") == []


def test_tokenize_only_stop_words():
    assert tokenize_query("a the and or") == []


# ---------------------------------------------------------------------------
# job_matches_query
# ---------------------------------------------------------------------------

def test_job_matches_by_title():
    tokens = tokenize_query("python fastapi")
    assert job_matches_query("Senior Python Developer", "", tokens) is True


def test_job_matches_by_description():
    tokens = tokenize_query("pgvector embeddings")
    assert job_matches_query("Backend Engineer", "We use pgvector for our search", tokens) is True


def test_job_no_match():
    tokens = tokenize_query("mobile ios swift")
    assert job_matches_query("Senior Python Developer", "fastapi postgres", tokens) is False


def test_job_matches_case_insensitive():
    tokens = tokenize_query("REACT")
    assert job_matches_query("React Developer", "", tokens) is True


# ---------------------------------------------------------------------------
# generate_lab_suggestions (mocked OpenAI)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_lab_suggestions_returns_parsed_suggestions():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        '{"query": "fractional CTO startup", "url_params": "contractor_tier=2,3&t=0,1", '
        '"reasoning": "covers CTO advisory gaps", "gap_jobs_targeted": ["CTO for SaaS"]}\n'
        '{"query": "saas mvp python", "url_params": "contractor_tier=2,3&t=0,1&hourly_rate=100-", '
        '"reasoning": "covers MVP gap", "gap_jobs_targeted": ["MVP Build"]}\n'
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.search_lab.AsyncOpenAI", return_value=mock_client):
        from app.services.search_lab import generate_lab_suggestions
        results = await generate_lab_suggestions(
            gap_titles=["CTO for SaaS", "MVP Build"],
            all_target_titles=["CTO for SaaS", "MVP Build", "API Work"],
            existing_queries=["python developer"],
            profile=None,
        )

    assert len(results) == 2
    assert results[0].query == "fractional CTO startup"
    assert results[1].query == "saas mvp python"


@pytest.mark.asyncio
async def test_generate_lab_suggestions_skips_invalid_json_lines():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        "not json at all\n"
        '{"query": "good query", "url_params": "contractor_tier=2,3&t=0,1", '
        '"reasoning": "reason", "gap_jobs_targeted": []}\n'
        "{broken json\n"
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.search_lab.AsyncOpenAI", return_value=mock_client):
        from app.services.search_lab import generate_lab_suggestions
        results = await generate_lab_suggestions([], [], [], None)

    assert len(results) == 1
    assert results[0].query == "good query"


@pytest.mark.asyncio
async def test_generate_lab_suggestions_caps_at_six():
    single = '{"query": "q%d", "url_params": "contractor_tier=2,3&t=0,1", "reasoning": "r", "gap_jobs_targeted": []}\n'
    raw = "".join(single % i for i in range(10))
    mock_response = MagicMock()
    mock_response.choices[0].message.content = raw
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.search_lab.AsyncOpenAI", return_value=mock_client):
        from app.services.search_lab import generate_lab_suggestions
        results = await generate_lab_suggestions([], [], [], None)

    assert len(results) == 6


# ---------------------------------------------------------------------------
# generate_optimize_variants (mocked OpenAI)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_optimize_variants_groups_by_query_id():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        '{"query_id": "q1", "query": "broader query", "url_params": "contractor_tier=2,3&t=0,1", '
        '"reasoning": "wider net", "change_type": "broader"}\n'
        '{"query_id": "q1", "query": "another variant", "url_params": "contractor_tier=2,3&t=0,1", '
        '"reasoning": "reframe", "change_type": "reframe"}\n'
        '{"query_id": "q2", "query": "q2 variant", "url_params": "contractor_tier=2,3&t=0,1", '
        '"reasoning": "for q2", "change_type": "narrower"}\n'
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    from app.schemas.search_query import QueryExperimentResult
    weak = [
        QueryExperimentResult(
            query_id="q1", query="old query", url_params="",
            jobs_returned=2, high_score_count=0, avg_score=0.0,
            sample_good_titles=[], sample_bad_titles=[],
        ),
        QueryExperimentResult(
            query_id="q2", query="other query", url_params="",
            jobs_returned=15, high_score_count=1, avg_score=0.3,
            sample_good_titles=[], sample_bad_titles=["junk"],
        ),
    ]

    with patch("app.services.search_lab.AsyncOpenAI", return_value=mock_client):
        from app.services.search_lab import generate_optimize_variants
        result = await generate_optimize_variants(weak, profile=None)

    assert "q1" in result
    assert "q2" in result
    assert len(result["q1"]) == 2
    assert result["q1"][0].query == "broader query"
    assert result["q1"][0].change_type == "broader"


@pytest.mark.asyncio
async def test_generate_optimize_variants_caps_per_query_at_three():
    single = (
        '{{"query_id": "q1", "query": "v{i}", "url_params": "contractor_tier=2,3&t=0,1", '
        '"reasoning": "r", "change_type": "broader"}}\n'
    )
    raw = "".join(single.format(i=i) for i in range(5))
    mock_response = MagicMock()
    mock_response.choices[0].message.content = raw
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    from app.schemas.search_query import QueryExperimentResult
    weak = [QueryExperimentResult(
        query_id="q1", query="q", url_params="",
        jobs_returned=1, high_score_count=0, avg_score=0.0,
        sample_good_titles=[], sample_bad_titles=[],
    )]

    with patch("app.services.search_lab.AsyncOpenAI", return_value=mock_client):
        from app.services.search_lab import generate_optimize_variants
        result = await generate_optimize_variants(weak, profile=None)

    assert len(result["q1"]) == 3


@pytest.mark.asyncio
async def test_generate_optimize_variants_empty_input():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content=""))]
    ))

    with patch("app.services.search_lab.AsyncOpenAI", return_value=mock_client):
        from app.services.search_lab import generate_optimize_variants
        result = await generate_optimize_variants([], profile=None)

    assert result == {}
