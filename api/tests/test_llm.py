"""Tests for the structured-output LLM seam (Anthropic client fully mocked)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services import llm
from app.services.llm import LLMError, structured_call

SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "integer"}},
    "required": ["a"],
    "additionalProperties": False,
}


def _fake_client(text: str = '{"a": 1}', stop_reason: str = "end_turn") -> MagicMock:
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    ))
    return client


@pytest.mark.asyncio
async def test_structured_call_sends_json_schema_and_effort():
    client = _fake_client()
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        result = await structured_call("claude-opus-5-5", "sys", "hello", SCHEMA, effort="high")

    assert result == {"a": 1}
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "hello"}]
    assert kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": SCHEMA},
        "effort": "high",
    }
    # Opus 5.5 rejects these — they must never be sent
    assert "temperature" not in kwargs
    assert "thinking" not in kwargs
    assert "tool_choice" not in kwargs


@pytest.mark.asyncio
async def test_structured_call_omits_effort_when_none():
    client = _fake_client()
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)
    assert "effort" not in client.messages.create.call_args.kwargs["output_config"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
async def test_structured_call_raises_on_bad_stop(stop_reason):
    with patch("app.services.llm.get_anthropic_client", return_value=_fake_client(stop_reason=stop_reason)):
        with pytest.raises(LLMError):
            await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)


@pytest.mark.asyncio
async def test_structured_call_raises_on_invalid_json():
    with patch("app.services.llm.get_anthropic_client", return_value=_fake_client(text="not json")):
        with pytest.raises(LLMError):
            await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)


@pytest.mark.asyncio
async def test_structured_call_prose_reply_names_the_proxy():
    """A proxy that strips output_config yields prose, not JSON."""
    prose = 'Sure! Here is the JSON you asked for:\n```json\n{"a": 1}\n```'
    with patch("app.services.llm.get_anthropic_client", return_value=_fake_client(text=prose)):
        with pytest.raises(LLMError, match="output_config"):
            await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)


@pytest.mark.asyncio
async def test_structured_call_wraps_api_errors():
    """A proxy that rejects output_config returns HTTP 400; callers only ever see LLMError."""
    import httpx
    from anthropic import BadRequestError

    request = httpx.Request("POST", "https://proxy.example.com/v1/messages")
    error = BadRequestError(
        "output_config: Extra inputs are not permitted",
        response=httpx.Response(400, request=request),
        body=None,
    )
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=error)
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        with pytest.raises(LLMError, match="output_config"):
            await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)


def test_get_anthropic_client_uses_base_url(monkeypatch):
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(settings, "anthropic_base_url", "https://proxy.example.com/")
    client = llm.get_anthropic_client()
    assert str(client.base_url) == "https://proxy.example.com/"
    assert llm.get_anthropic_client() is client
    monkeypatch.setattr(llm, "_client", None)


def test_extraction_model_default():
    assert settings.extraction_model == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_invalid_json_log_never_contains_model_output(caplog):
    secret = "Client Jane Doe paid $90k, phone 555-0100 {not json"
    client = _fake_client(text=secret)
    client.messages.create.return_value.usage = SimpleNamespace(input_tokens=11, output_tokens=22)
    with caplog.at_level("DEBUG", logger="app.services.llm"):
        with patch("app.services.llm.get_anthropic_client", return_value=client):
            with pytest.raises(LLMError):
                await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)
    logged = caplog.text
    assert "Jane" not in logged and "555-0100" not in logged and "not json" not in logged
    assert "claude-haiku-4-5" in logged
    assert "end_turn" in logged
    assert str(len(secret)) in logged
    assert "22" in logged


def test_model_defaults():
    from app.core.config import Settings

    fields = Settings.model_fields
    assert fields["cover_letter_model"].default == "claude-opus-5-5"
    assert fields["extraction_model"].default == "claude-haiku-4-5"
    assert fields["writer_effort"].default == "high"
    assert fields["legacy_cover_letter_model"].default == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_structured_call_passes_cached_system_blocks_through():
    blocks = [{"type": "text", "text": "rules", "cache_control": {"type": "ephemeral"}}]
    client = _fake_client()
    client.messages.create.return_value.usage = SimpleNamespace(
        input_tokens=10, output_tokens=5, cache_read_input_tokens=8, cache_creation_input_tokens=0
    )
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        assert await structured_call("claude-opus-5-5", blocks, "u", SCHEMA) == {"a": 1}
    assert client.messages.create.call_args.kwargs["system"] == blocks
