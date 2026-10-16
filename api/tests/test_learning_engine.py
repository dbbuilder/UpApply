"""Regression: winning_proposal_to_memory never writes a corpus memory (phase 0).

Spec §1.1: retrievable stores never hold job postings or unedited AI drafts.
The queue's draft_cover_letter is an unedited AI draft and the memory text
would embed the client's job post, so the path stays inert until Phase 3
retires it in favour of fact crediting.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agent.learning_engine as learning_engine
from agent.learning_engine import winning_proposal_to_memory


@pytest.mark.asyncio
async def test_winning_proposal_to_memory_writes_nothing():
    db = MagicMock()
    db.flush = AsyncMock()
    embed = AsyncMock(return_value=[0.2] * 1536)

    with patch.object(learning_engine, "generate_embedding", embed, create=True):
        result = await winning_proposal_to_memory(
            user_id="user-1",
            job_title="Fractional CTO for seed-stage SaaS",
            job_description="Need architecture leadership for a 6-person team.",
            cover_letter_text="That platform was taken from zero to exit.",
            db=db,
        )

    assert result is None
    db.add.assert_not_called()
    db.flush.assert_not_called()
    embed.assert_not_called()
