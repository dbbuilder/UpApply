"""OpenAI embeddings service for semantic search."""
import hashlib
import logging
from collections import OrderedDict
from typing import List
from openai import AsyncOpenAI, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)

# Guard: only send the quota alert once per process lifetime.
_quota_alert_sent = False

# In-process LRU cache for embeddings — eliminates duplicate API calls within
# the same server instance (e.g. job saved then immediately re-analyzed).
# Keyed on sha256 of the first 2 000 chars of the input text.
_EMBED_CACHE: "OrderedDict[str, List[float]]" = OrderedDict()
_EMBED_CACHE_MAX = 512


def _embed_cache_key(text: str) -> str:
    return hashlib.sha256(text[:2000].encode()).hexdigest()


def _send_quota_alert() -> None:
    """Fire a one-shot Resend email when the OpenAI quota is exhausted."""
    global _quota_alert_sent
    if _quota_alert_sent or not settings.resend_api_key:
        return
    _quota_alert_sent = True
    try:
        import resend
        resend.api_key = settings.resend_api_key
        resend.Emails.send({
            "from": "noreply@servicevision.net",
            "to": [settings.alert_email],
            "subject": "⚠️ UpApply: OpenAI quota exhausted",
            "html": (
                "<p>The OpenAI API key used by UpApply has hit its quota limit "
                "(<code>insufficient_quota</code>).</p>"
                "<p>Job analysis is falling back to rule-based scoring — "
                "embedding search and LLM scoring are disabled until the quota is refilled.</p>"
                "<p><a href='https://platform.openai.com/settings/billing'>"
                "Top up at platform.openai.com/settings/billing</a></p>"
            ),
        })
        logger.info("OpenAI quota alert sent to %s", settings.alert_email)
    except Exception as exc:
        logger.warning("Failed to send quota alert email: %s", exc)


# Initialize OpenAI client
_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """Get or create OpenAI async client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def _generate_embedding_api(text: str) -> List[float]:
    """Call the OpenAI embeddings API (retried on transient errors)."""
    client = get_openai_client()
    try:
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=text,
            dimensions=settings.embedding_dimensions,
        )
        return response.data[0].embedding
    except RateLimitError as exc:
        if "insufficient_quota" in str(exc):
            _send_quota_alert()
        raise


async def generate_embedding(text: str) -> List[float]:
    """Generate embedding for a text string, with in-process LRU caching."""
    key = _embed_cache_key(text)
    if key in _EMBED_CACHE:
        _EMBED_CACHE.move_to_end(key)
        return _EMBED_CACHE[key]

    result = await _generate_embedding_api(text)

    _EMBED_CACHE[key] = result
    if len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
        _EMBED_CACHE.popitem(last=False)
    return result


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts in batch."""
    if not texts:
        return []

    client = get_openai_client()

    # OpenAI has a limit on batch size, process in chunks
    chunk_size = 100
    all_embeddings = []

    for i in range(0, len(texts), chunk_size):
        chunk = texts[i : i + chunk_size]
        try:
            response = await client.embeddings.create(
                model=settings.embedding_model,
                input=chunk,
                dimensions=settings.embedding_dimensions,
            )
        except RateLimitError as exc:
            if "insufficient_quota" in str(exc):
                _send_quota_alert()
            raise
        all_embeddings.extend([item.embedding for item in response.data])

    return all_embeddings
