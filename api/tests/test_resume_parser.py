"""Tests for resume_parser service (mocked — no real OpenAI calls)."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_response(content: dict) -> MagicMock:
    """Construct a minimal mock that looks like an OpenAI chat completion."""
    msg = MagicMock()
    msg.content = json.dumps(content)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


MINIMAL_RESUME = """
John Doe
Senior Python Developer
5 years of Python, FastAPI, PostgreSQL.
Built payment processing API processing $2M/day.
"""

EXPECTED_PARSE_RESULT = {
    "full_name": "John Doe",
    "professional_title": "Senior Python Developer",
    "bio": "Experienced Python developer with 5 years building APIs.",
    "skills": [
        {"name": "Python", "level": "expert", "years": 5},
        {"name": "FastAPI", "level": "expert", "years": 3},
    ],
    "work_history": [
        {
            "title": "Senior Python Developer",
            "company": "Acme Corp",
            "duration": "2020-2025",
            "description": "Built payment APIs",
            "highlights": ["Processing $2M/day"],
        }
    ],
    "education": [],
    "certifications": [],
    "memories": [
        {
            "title": "Payment API",
            "content": "Built payment processing API processing $2M/day",
            "category": "project",
            "skills_demonstrated": ["Python", "FastAPI"],
            "outcome": "$2M/day throughput",
        }
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_resume_happy_path():
    """parse_resume returns parsed dict on success."""
    from app.services.resume_parser import parse_resume

    mock_resp = _make_openai_response(EXPECTED_PARSE_RESULT)

    with patch("app.services.resume_parser.get_openai_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        mock_client_factory.return_value = mock_client

        result = await parse_resume(MINIMAL_RESUME)

    assert result["full_name"] == "John Doe"
    assert result["professional_title"] == "Senior Python Developer"
    assert len(result["skills"]) == 2
    assert result["memories"][0]["category"] == "project"


@pytest.mark.asyncio
async def test_parse_resume_uses_correct_model():
    """parse_resume passes settings.default_model to the API call."""
    from app.services.resume_parser import parse_resume
    from app.core.config import settings

    mock_resp = _make_openai_response(EXPECTED_PARSE_RESULT)
    captured_kwargs: dict = {}

    async def fake_create(**kwargs):
        captured_kwargs.update(kwargs)
        return mock_resp

    with patch("app.services.resume_parser.get_openai_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create = fake_create
        mock_client_factory.return_value = mock_client

        await parse_resume(MINIMAL_RESUME)

    assert captured_kwargs["model"] == settings.default_model
    assert captured_kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_parse_resume_retries_on_failure():
    """parse_resume retries up to 3 times via tenacity."""
    from app.services.resume_parser import parse_resume

    mock_resp = _make_openai_response(EXPECTED_PARSE_RESULT)
    call_count = 0

    async def flaky_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise Exception("transient error")
        return mock_resp

    with patch("app.services.resume_parser.get_openai_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create = flaky_create
        mock_client_factory.return_value = mock_client

        result = await parse_resume(MINIMAL_RESUME)

    assert call_count == 2
    assert result["full_name"] == "John Doe"


@pytest.mark.asyncio
async def test_parse_resume_empty_text():
    """parse_resume works with minimal/empty resume text."""
    from app.services.resume_parser import parse_resume

    minimal = {"full_name": None, "professional_title": "", "bio": "",
               "skills": [], "work_history": [], "education": [],
               "certifications": [], "memories": []}
    mock_resp = _make_openai_response(minimal)

    with patch("app.services.resume_parser.get_openai_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        mock_client_factory.return_value = mock_client

        result = await parse_resume("")

    assert result["full_name"] is None
    assert result["skills"] == []


@pytest.mark.asyncio
async def test_parse_resume_includes_resume_text_in_prompt():
    """parse_resume appends the resume text to the user message."""
    from app.services.resume_parser import parse_resume

    resume_text = "Unique marker: XYZ-789-ABC"
    mock_resp = _make_openai_response(EXPECTED_PARSE_RESULT)
    captured_messages: list = []

    async def capture_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return mock_resp

    with patch("app.services.resume_parser.get_openai_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create = capture_create
        mock_client_factory.return_value = mock_client

        await parse_resume(resume_text)

    user_message = next(m for m in captured_messages if m["role"] == "user")
    assert resume_text in user_message["content"]
