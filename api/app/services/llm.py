"""Anthropic structured-output seam for the memory-driven generation pipeline.

Every new LLM call goes through structured_call so tests mock one function.
Honours Opus 5.5 constraints: no temperature, no thinking param (effort is the
only depth control), no assistant prefill, no forced tool_choice — the response
shape comes from output_config.format (JSON-schema structured outputs).
"""
import json
import logging
from typing import Optional, Union

from anthropic import APIError, AsyncAnthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncAnthropic] = None
_writer_client: Optional[AsyncAnthropic] = None

# Shown when the reply is not the requested JSON: the usual cause is a proxy
# (ANTHROPIC_BASE_URL) that drops or rejects output_config.
PROXY_HINT = "check that ANTHROPIC_BASE_URL passes output_config through"


class LLMError(RuntimeError):
    """A structured call produced no usable JSON (refusal, truncation, bad JSON). `reason` is a
    fixed category that is safe to log; the message may hold upstream text and is not."""

    def __init__(self, message: str, reason: str = "unknown"):
        super().__init__(message)
        self.reason = reason


def get_anthropic_client() -> AsyncAnthropic:
    """Process-wide AsyncAnthropic client; honours ANTHROPIC_BASE_URL (AICostCentral proxy)."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url or None,
        )
    return _client


def get_writer_client() -> AsyncAnthropic:
    """The cover-letter writer's client: a direct Anthropic client when WRITER_ANTHROPIC_API_KEY
    is set, otherwise the shared client (proxy)."""
    global _writer_client
    if not settings.writer_anthropic_api_key:
        return get_anthropic_client()
    if _writer_client is None:
        _writer_client = AsyncAnthropic(
            api_key=settings.writer_anthropic_api_key,
            base_url=settings.writer_anthropic_base_url or None,
        )
    return _writer_client


async def structured_call(
    model: str,
    system: Union[str, list],
    user: str,
    schema: dict,
    effort: Optional[str] = None,
    max_tokens: int = 16000,
    writer: bool = False,
    api_retries: int = 0,
) -> dict:
    """Single-turn call whose reply is guaranteed to match `schema`; returns the parsed dict.
    `writer=True` routes through get_writer_client(); `api_retries` re-sends the call that many
    times after an API error the SDK's own retries did not clear (Q11 C)."""
    output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config["effort"] = effort

    client = get_writer_client() if writer else get_anthropic_client()
    for attempt in range(api_retries + 1):
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config=output_config,
            )
            break
        except APIError as exc:
            if attempt < api_retries:
                logger.warning("structured_call %s API error (%s); retrying %d/%d",
                               model, type(exc).__name__, attempt + 1, api_retries)
                continue
            raise LLMError(f"structured_call API error from {model}: {exc} ({PROXY_HINT})", reason="api_error") from exc

    # Usage only — never prompt or output content.
    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "llm model=%s stop_reason=%s in=%s out=%s cache_read=%s cache_write=%s",
            model,
            response.stop_reason,
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
            getattr(usage, "cache_read_input_tokens", None),
            getattr(usage, "cache_creation_input_tokens", None),
        )

    if response.stop_reason in ("refusal", "max_tokens"):
        raise LLMError(f"structured_call stopped with {response.stop_reason} (model={model})", reason=str(response.stop_reason))

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise LLMError(f"structured_call returned no text block (model={model})", reason="no_text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Never log the output itself: it can carry client/user data.
        logger.warning(
            "structured_call invalid JSON from %s (stop_reason=%s, output_chars=%d, usage=%s)",
            model, response.stop_reason, len(text), getattr(response, "usage", None),
        )
        raise LLMError(f"structured_call returned invalid JSON (model={model}; {PROXY_HINT})", reason="invalid_json") from exc
