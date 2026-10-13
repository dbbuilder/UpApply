"""Schema tests for the knowledge layer (facts + voice-sample + memory flag columns)."""
import pytest
from sqlalchemy import select

from app.models.fact import Fact
from app.models.memory import Memory
from app.models.proposal import Proposal
from tests.vector_utils import unit


@pytest.mark.asyncio
async def test_fact_roundtrip_with_defaults(db_session, test_user):
    fact = Fact(
        user_id=test_user.id,
        kind="metric",
        statement="Migrated a 160-server datacenter to Azure.",
        skills=["Azure", "SQL Server"],
        job_types=["cloud"],
        source_type="bio_memory",
        sources=[{"source_type": "bio_memory", "source_ref": "m1", "snippet": "160 servers"}],
        embedding=unit(0),
    )
    db_session.add(fact)
    await db_session.commit()

    row = (await db_session.execute(select(Fact).where(Fact.id == fact.id))).scalar_one()
    assert row.status == "candidate"
    assert row.strength == 0.5
    assert row.times_used == 0
    assert row.times_in_won == 0
    assert row.skills == ["Azure", "SQL Server"]
    assert row.industries == []
    assert row.job_types == ["cloud"]
    assert row.sources[0]["source_ref"] == "m1"
    assert len(row.embedding) == 1536


@pytest.mark.asyncio
async def test_proposal_voice_sample_columns_default(db_session, test_user):
    proposal = Proposal(user_id=test_user.id, cover_letter_text="Letter body", source="scraped")
    db_session.add(proposal)
    await db_session.commit()

    row = (await db_session.execute(select(Proposal).where(Proposal.id == proposal.id))).scalar_one()
    assert row.author == "chris"
    assert row.outcome is None
    assert row.job_text is None
    assert row.screening_answers is None
    assert row.job_needs_embedding is None
    assert row.facts_ingested_at is None


@pytest.mark.asyncio
async def test_memory_exclude_flag_defaults_false(db_session, test_user):
    memory = Memory(user_id=test_user.id, title="Bio", content="Built Stratavault.ai")
    db_session.add(memory)
    await db_session.commit()

    row = (await db_session.execute(select(Memory).where(Memory.id == memory.id))).scalar_one()
    assert row.exclude_from_retrieval is False
