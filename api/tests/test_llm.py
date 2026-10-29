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


class _FakeStream:
    """Stands in for the SDK's AsyncMessageStreamManager / AsyncMessageStream pair."""

    def __init__(self, response=None, error: Exception = None):
        self.response, self.error = response, error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        if self.error is not None:
            raise self.error
        return self.response


def _fake_client(text: str = '{"a": 1}', stop_reason: str = "end_turn", error: Exception = None) -> MagicMock:
    """`client.response` is the final message, so tests can attach usage to it."""
    client = MagicMock()
    client.response = SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )
    client.messages.stream = MagicMock(return_value=_FakeStream(client.response, error))
    client.messages.create = AsyncMock(side_effect=AssertionError("structured_call must stream"))
    return client


@pytest.mark.asyncio
async def test_structured_call_sends_json_schema_and_effort():
    client = _fake_client()
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        result = await structured_call("claude-opus-5-5", "sys", "hello", SCHEMA, effort="high")

    assert result == {"a": 1}
    kwargs = client.messages.stream.call_args.kwargs
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
    assert "effort" not in client.messages.stream.call_args.kwargs["output_config"]


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
    client.messages.stream = MagicMock(side_effect=error)
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        with pytest.raises(LLMError, match="output_config"):
            await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)


@pytest.mark.asyncio
async def test_structured_call_streams_so_the_proxy_sees_bytes_early():
    """Long Opus writer calls made non-streaming drew 504s from the AI proxy; the call streams
    and still returns the parsed final message."""
    client = _fake_client()
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        assert await structured_call("claude-opus-5-5", "sys", "hello", SCHEMA, effort="high") == {"a": 1}
    client.messages.stream.assert_called_once()
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_structured_call_wraps_a_504_from_the_proxy():
    import httpx2
    from anthropic import InternalServerError

    request = httpx2.Request("POST", "https://proxy.example.com/v1/messages")
    error = InternalServerError(
        "An error occurred with your deployment", response=httpx2.Response(504, request=request), body=None
    )
    with patch("app.services.llm.get_anthropic_client", return_value=_fake_client(error=error)):
        with pytest.raises(LLMError, match="output_config") as info:
            await structured_call("claude-opus-5-5", "sys", "hello", SCHEMA)
    assert info.value.reason == "api_error"


@pytest.mark.asyncio
async def test_structured_call_wraps_a_stream_dropped_midway(caplog):
    """A connection cut mid-stream is a raw transport error, not an APIError; callers still
    only ever see LLMError."""
    import httpx2

    error = httpx2.RemoteProtocolError("peer closed connection without sending complete message body")
    with caplog.at_level("WARNING", logger="app.services.llm"):
        with patch("app.services.llm.get_anthropic_client", return_value=_fake_client(error=error)):
            with pytest.raises(LLMError) as info:
                await structured_call("claude-opus-5-5", "sys", "hello", SCHEMA)
    assert info.value.reason == "stream_interrupted"
    assert "RemoteProtocolError" in caplog.text


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
    client.response.usage = SimpleNamespace(input_tokens=11, output_tokens=22)
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
    client.response.usage = SimpleNamespace(
        input_tokens=10, output_tokens=5, cache_read_input_tokens=8, cache_creation_input_tokens=0
    )
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        assert await structured_call("claude-opus-5-5", blocks, "u", SCHEMA) == {"a": 1}
    assert client.messages.stream.call_args.kwargs["system"] == blocks


@pytest.mark.asyncio
async def test_structured_call_through_the_real_sdk_stream():
    """No network: the installed SDK's stream helper sends stream=true with output_config intact
    and assembles the SSE text deltas into the JSON reply."""
    import json

    import httpx2
    from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient

    events = [
        {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": '{"a": '}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "1}"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 5}},
        {"type": "message_stop"},
    ]
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())

    client = AsyncAnthropic(
        api_key="x", base_url="https://proxy.example.com",
        http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        assert await structured_call("claude-opus-5-5", "sys", "u", SCHEMA, effort="high") == {"a": 1}
    assert sent["stream"] is True
    assert sent["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}, "effort": "high"}
    assert not {"temperature", "thinking", "tool_choice"} & set(sent)
