"""Deterministic fake embeddings for pgvector tests (no OpenAI calls)."""
import math
from unittest.mock import AsyncMock

DIM = 1536


def unit(i: int) -> list[float]:
    """Unit vector along axis i — orthogonal (cosine 0) to every other axis."""
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def blend(i: int, j: int, cos: float) -> list[float]:
    """Unit vector whose cosine similarity to unit(i) is exactly `cos`."""
    v = [0.0] * DIM
    v[i] = cos
    v[j] = math.sqrt(1.0 - cos * cos)
    return v


def make_fake_embedder() -> AsyncMock:
    """AsyncMock embedder: identical text -> identical vector, distinct text -> orthogonal vector."""
    vectors: dict[str, list[float]] = {}

    def _embed(text: str) -> list[float]:
        if text not in vectors:
            vectors[text] = unit(len(vectors) % DIM)
        return vectors[text]

    return AsyncMock(side_effect=_embed)
