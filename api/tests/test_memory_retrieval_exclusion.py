"""Corpus JOB POSTING memories flagged exclude_from_retrieval must not reach generation."""
import pytest

from app.models.memory import Memory
from app.services.job_analysis import find_relevant_memories_with_embedding
from tests.vector_utils import unit


@pytest.mark.asyncio
async def test_excluded_memories_are_not_retrieved(db_session, test_user):
    db_session.add_all([
        Memory(user_id=test_user.id, title="Bio", content="Built Stratavault.ai", embedding=unit(5)),
        Memory(
            user_id=test_user.id, title="Past Proposal: X",
            content="JOB POSTING:\nNeed a dev\n\nPROPOSAL WRITTEN:\n...",
            embedding=unit(5), exclude_from_retrieval=True,
        ),
    ])
    await db_session.commit()

    results = await find_relevant_memories_with_embedding(db_session, test_user.id, unit(5), limit=5)
    assert [m["title"] for m in results] == ["Bio"]
