"""OpenAI embeddings service for semantic search."""
from typing import List
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


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
async def generate_embedding(text: str) -> List[float]:
    """Generate embedding for a text string using OpenAI."""
    client = get_openai_client()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=settings.embedding_dimensions,
    )
    return response.data[0].embedding


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
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=chunk,
            dimensions=settings.embedding_dimensions,
        )
        all_embeddings.extend([item.embedding for item in response.data])

    return all_embeddings
