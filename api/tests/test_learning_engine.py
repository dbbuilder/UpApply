"""Regression: winning_proposal_to_memory builds a valid Memory row (phase 0)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.learning_engine import winning_proposal_to_memory
from app.models.memory import Memory


@pytest.mark.asyncio
async def test_winning_proposal_to_memory_adds_valid_memory():
    db = MagicMock()
    db.flush = AsyncMock()

    with patch("agent.learning_engine.generate_embedding", AsyncMock(return_value=[0.2] * 1536)):
        await winning_proposal_to_memory(
            user_id="user-1",
            job_title="Fractional CTO for seed-stage SaaS",
            job_description="Need architecture leadership for a 6-person team.",
            cover_letter_text="That platform was taken from zero to exit.",
            db=db,
        )

    db.add.assert_called_once()
    memory = db.add.call_args.args[0]
    assert isinstance(memory, Memory)
    assert memory.user_id == "user-1"
    assert memory.title == "Won: Fractional CTO for seed-stage SaaS"
    assert "WINNING COVER LETTER:\nThat platform was taken from zero to exit." in memory.content
    assert memory.category == "achievement"
    assert memory.source == "job_won"
    assert memory.importance_score == 0.95
    assert memory.embedding == [0.2] * 1536
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_winning_proposal_to_memory_truncates_long_title():
    db = MagicMock()
    db.flush = AsyncMock()

    with patch("agent.learning_engine.generate_embedding", AsyncMock(return_value=[0.2] * 1536)):
        await winning_proposal_to_memory(
            user_id="user-1",
            job_title="x" * 600,
            job_description="",
            cover_letter_text="Body",
            db=db,
        )

    assert len(db.add.call_args.args[0].title) == 500
