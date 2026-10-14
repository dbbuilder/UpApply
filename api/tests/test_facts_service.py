"""Facts service: dedupe/merge/auto-approve, search, credit (embeddings mocked)."""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.models.fact import Fact
from app.schemas.fact import FactCandidate
from app.services.facts import (
    DEDUPE_THRESHOLD,
    credit_facts,
    search_facts,
    upsert_candidate,
    upsert_candidate_outcome,
)
from tests.vector_utils import blend, unit


def _cand(statement: str, strength: float = 0.7, **kw) -> FactCandidate:
    return FactCandidate(
        kind=kw.pop("kind", "metric"),
        statement=statement,
        strength=strength,
        source_type=kw.pop("source_type", "upwork_proposal"),
        source_ref=kw.pop("source_ref", "p1"),
        source_snippet=kw.pop("source_snippet", "snippet"),
        **kw,
    )


async def _seed(db, user_id, statement, embedding, status="candidate", strength=0.6, **kw) -> Fact:
    fact = Fact(
        user_id=user_id, kind="metric", statement=statement, status=status, strength=strength,
        source_type="bio_memory", source_ref="m1",
        sources=[{"source_type": "bio_memory", "source_ref": "m1", "snippet": None}],
        embedding=embedding, **kw,
    )
    db.add(fact)
    await db.flush()
    return fact


async def _count(db) -> int:
    return (await db.execute(select(func.count()).select_from(Fact))).scalar_one()


def test_threshold_constant():
    assert DEDUPE_THRESHOLD == 0.92


@pytest.mark.asyncio
async def test_new_candidate_is_created(db_session, test_user):
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(0))):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id, _cand("Cut Azure spend 38%.", skills=["Azure"], job_types=["cloud"])
        )
    assert outcome == "created"
    assert fact.status == "candidate"
    assert fact.skills == ["Azure"]
    assert fact.sources == [{"source_type": "upwork_proposal", "source_ref": "p1", "snippet": "snippet"}]
    assert fact.source_type == "upwork_proposal"


@pytest.mark.asyncio
async def test_match_to_approved_auto_approves_and_keeps_wording(db_session, test_user):
    existing = await _seed(
        db_session, test_user.id, "Migrated 160 servers to Azure.", unit(0),
        status="approved", strength=0.6, skills=["Azure"],
    )
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=blend(0, 1, 0.95))):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id,
            _cand("Moved 160 on-prem servers into Azure.", strength=0.9, skills=["SQL Server"]),
        )
    assert outcome == "auto_approved"
    assert fact.id == existing.id
    assert fact.statement == "Migrated 160 servers to Azure."
    # untrusted candidate: provenance only, ranking fields untouched
    assert fact.strength == 0.6
    assert fact.skills == ["Azure"]
    assert [s["source_ref"] for s in fact.sources] == ["m1", "p1"]
    assert await _count(db_session) == 1


@pytest.mark.asyncio
async def test_untrusted_merge_into_approved_only_appends_provenance(db_session, test_user):
    existing = await _seed(
        db_session, test_user.id, "Migrated 160 servers to Azure.", unit(0),
        status="approved", strength=0.5, skills=["Azure"], industries=["Education"], job_types=["cloud"],
    )
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(0))):
        fact, _ = await upsert_candidate_outcome(
            db_session, test_user.id,
            _cand("Migrated 160 servers to Azure.", strength=1.0, skills=["AI", "Kubernetes"],
                  industries=["Fintech"], job_types=["ai", "cto"], source_type="chatgpt_user_turn"),
        )
    assert fact.id == existing.id and fact.status == "approved"
    assert fact.strength == 0.5
    assert fact.skills == ["Azure"]
    assert fact.industries == ["Education"]
    assert fact.job_types == ["cloud"]
    assert [s["source_type"] for s in fact.sources] == ["bio_memory", "chatgpt_user_turn"]


@pytest.mark.asyncio
async def test_trusted_auto_approve_merge_into_approved_updates_ranking(db_session, test_user):
    await _seed(
        db_session, test_user.id, "Migrated 160 servers to Azure.", unit(0),
        status="approved", strength=0.5, skills=["Azure"], job_types=["cloud"],
    )
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(0))):
        fact, _ = await upsert_candidate_outcome(
            db_session, test_user.id,
            _cand("Migrated 160 servers to Azure.", strength=0.9, skills=["SQL Server"],
                  job_types=["sql"], source_type="bio_memory"),
            auto_approve=True,
        )
    assert fact.strength == 0.9
    assert fact.skills == ["Azure", "SQL Server"]
    assert fact.job_types == ["cloud", "sql"]


@pytest.mark.asyncio
async def test_match_to_candidate_merges_and_takes_stronger_wording(db_session, test_user):
    existing = await _seed(db_session, test_user.id, "Did an Azure migration.", unit(0), strength=0.4)
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=blend(0, 1, 0.93))):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id, _cand("Migrated 160 servers to Azure.", strength=0.9)
        )
    assert outcome == "merged"
    assert fact.id == existing.id
    assert fact.status == "candidate"
    assert fact.statement == "Migrated 160 servers to Azure."
    assert fact.strength == 0.9


@pytest.mark.asyncio
async def test_auto_approve_promotes_matched_candidate(db_session, test_user):
    await _seed(db_session, test_user.id, "Founded a SaaS company in 2001.", unit(0))
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=blend(0, 1, 0.97))):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id, _cand("Founded a SaaS company in 2001.", source_type="bio_memory"),
            auto_approve=True,
        )
    assert outcome == "auto_approved"
    assert fact.status == "approved"


@pytest.mark.asyncio
async def test_rejected_match_stays_rejected(db_session, test_user):
    await _seed(db_session, test_user.id, "Knows Excel.", unit(0), status="rejected")
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(0))):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id, _cand("Knows Excel."), auto_approve=True
        )
    assert outcome == "merged"
    assert fact.status == "rejected"
    assert await _count(db_session) == 1


@pytest.mark.asyncio
async def test_below_threshold_creates_new_row(db_session, test_user):
    await _seed(db_session, test_user.id, "Migrated 160 servers to Azure.", unit(0), status="approved")
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=blend(0, 1, 0.85))):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id, _cand("Optimised Azure SQL costs.")
        )
    assert outcome == "created"
    assert await _count(db_session) == 2


@pytest.mark.asyncio
async def test_auto_approve_new_fact_and_wrapper_returns_fact(db_session, test_user):
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(4))):
        fact = await upsert_candidate(
            db_session, test_user.id, _cand("Holds an MBA.", kind="credential"), auto_approve=True
        )
    assert isinstance(fact, Fact)
    assert fact.status == "approved"


@pytest.mark.asyncio
async def test_search_returns_only_requested_status_sorted(db_session, test_user):
    a = await _seed(db_session, test_user.id, "A", unit(0), status="approved")
    b = await _seed(db_session, test_user.id, "B", blend(0, 1, 0.5), status="approved")
    await _seed(db_session, test_user.id, "C", unit(0), status="candidate")

    results = await search_facts(db_session, test_user.id, unit(0), limit=8)
    assert [f.id for f, _ in results] == [a.id, b.id]
    assert results[0][1] == pytest.approx(1.0, abs=1e-6)
    assert results[1][1] == pytest.approx(0.5, abs=1e-6)

    candidates = await search_facts(db_session, test_user.id, unit(0), status="candidate")
    assert [f.statement for f, _ in candidates] == ["C"]


@pytest.mark.asyncio
async def test_credit_facts_increments_counters(db_session, test_user):
    fact = await _seed(db_session, test_user.id, "A", unit(0), status="approved")
    await credit_facts(db_session, [fact.id], won=False, user_id=test_user.id)
    await credit_facts(db_session, [fact.id], won=False, user_id=test_user.id)
    await credit_facts(db_session, [fact.id], won=True, user_id=test_user.id)
    await credit_facts(db_session, [], won=True, user_id=test_user.id)
    await db_session.refresh(fact)
    assert fact.times_used == 2
    assert fact.times_in_won == 1


async def _other_user(db):
    from app.models.user import User

    user = User(email="facts-other@example.com", hashed_password="not-a-real-hash")
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_dedupe_never_matches_another_users_fact(db_session, test_user):
    other = await _other_user(db_session)
    theirs = await _seed(db_session, other.id, "Migrated 160 servers to Azure.", unit(0), status="approved")
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(0))):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id, _cand("Migrated 160 servers to Azure.")
        )
    assert outcome == "created"
    assert fact.id != theirs.id
    assert fact.user_id == test_user.id
    await db_session.refresh(theirs)
    assert len(theirs.sources) == 1


@pytest.mark.asyncio
async def test_search_is_scoped_to_user(db_session, test_user):
    other = await _other_user(db_session)
    await _seed(db_session, other.id, "Theirs", unit(0), status="approved")
    mine = await _seed(db_session, test_user.id, "Mine", unit(0), status="approved")
    results = await search_facts(db_session, test_user.id, unit(0))
    assert [f.id for f, _ in results] == [mine.id]


@pytest.mark.asyncio
async def test_credit_facts_ignores_other_users_facts(db_session, test_user):
    other = await _other_user(db_session)
    theirs = await _seed(db_session, other.id, "Theirs", unit(0), status="approved")
    await credit_facts(db_session, [theirs.id], won=True, user_id=test_user.id)
    await db_session.refresh(theirs)
    assert theirs.times_in_won == 0


@pytest.mark.asyncio
async def test_auto_approve_into_untrusted_candidate_takes_trusted_wording(db_session, test_user):
    """A bio-memory match must never approve an unreviewed candidate's own (untrusted) wording."""
    existing = await _seed(db_session, test_user.id, "Led the biggest-ever 160-server Azure migration.", unit(0), strength=1.0)
    trusted_vec = blend(0, 1, 0.95)
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=trusted_vec)):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id,
            _cand("Led a 160-server on-prem to Azure migration.", strength=0.9, source_type="bio_memory", kind="project"),
            auto_approve=True,
        )
    assert outcome == "auto_approved"
    assert fact.id == existing.id
    assert fact.status == "approved"
    assert fact.statement == "Led a 160-server on-prem to Azure migration."
    assert fact.kind == "project"
    assert list(fact.embedding) == pytest.approx(trusted_vec)


async def _force_hnsw(db):
    """Make the planner use the HNSW index with a tiny candidate list, as on a large table.

    The btree indexes are dropped inside this (never committed) transaction so the planner
    cannot pick them on a tiny test table; the session rollback restores them."""
    from sqlalchemy import text

    await db.execute(text("DROP INDEX ix_facts_user_status"))
    await db.execute(text("DROP INDEX ix_facts_user_id"))
    await db.execute(text("SET LOCAL enable_seqscan = off"))
    await db.execute(text("SET LOCAL hnsw.ef_search = 10"))


@pytest.mark.asyncio
async def test_search_recall_survives_closer_rows_of_other_users_and_statuses(db_session, test_user):
    other = await _other_user(db_session)
    for k in range(2, 152):
        await _seed(db_session, other.id, f"theirs {k}", blend(0, k, 0.9), status="approved")
    for k in range(152, 202):
        await _seed(db_session, test_user.id, f"mine cand {k}", blend(0, k, 0.9), status="candidate")
    mine = await _seed(db_session, test_user.id, "Mine approved", blend(0, 1, 0.5), status="approved")
    await _force_hnsw(db_session)

    results = await search_facts(db_session, test_user.id, unit(0), limit=5)
    assert [f.id for f, _ in results] == [mine.id]
    assert results[0][1] == pytest.approx(0.5, abs=1e-6)


@pytest.mark.asyncio
async def test_dedupe_recall_survives_closer_rows_of_other_users(db_session, test_user):
    other = await _other_user(db_session)
    for k in range(2, 202):
        await _seed(db_session, other.id, f"theirs {k}", blend(0, k, 0.99), status="approved")
    mine = await _seed(db_session, test_user.id, "Migrated 160 servers.", blend(0, 1, 0.95), status="approved")
    await _force_hnsw(db_session)

    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(0))):
        fact, _ = await upsert_candidate_outcome(db_session, test_user.id, _cand("Moved 160 servers."))
    assert fact.id == mine.id


@pytest.mark.parametrize("source_type,kind", [
    ("client_feedback", "outcome"),
    ("upwork_contract", "project"),
    ("chatgpt_user_turn", "client_quote"),
])
@pytest.mark.asyncio
async def test_client_sourced_candidate_into_approved_merges_provenance_only(db_session, test_user, source_type, kind):
    existing = await _seed(db_session, test_user.id, "Saved the launch.", unit(0),
                           status="approved", strength=0.5, skills=["Azure"])
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(0))):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id,
            _cand("Saved the launch!", strength=1.0, skills=["AI"], source_type=source_type, kind=kind),
            auto_approve=True,
        )
    assert fact.id == existing.id
    assert outcome == "merged"
    assert fact.statement == "Saved the launch."
    assert fact.strength == 0.5 and fact.skills == ["Azure"]
    assert [s["source_type"] for s in fact.sources] == ["bio_memory", source_type]


@pytest.mark.parametrize("source_type,kind", [
    ("client_feedback", "outcome"),
    ("upwork_contract", "project"),
    ("chatgpt_user_turn", "client_quote"),
])
@pytest.mark.asyncio
async def test_client_sourced_candidates_are_never_auto_approved(db_session, test_user, source_type, kind):
    pending = await _seed(db_session, test_user.id, "Pending wording.", unit(1), status="candidate", strength=0.4)
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(0))):
        new, outcome_new = await upsert_candidate_outcome(
            db_session, test_user.id, _cand("Brand new claim.", source_type=source_type, kind=kind), auto_approve=True,
        )
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(1))):
        merged, outcome_merged = await upsert_candidate_outcome(
            db_session, test_user.id, _cand("Stronger wording.", strength=1.0, source_type=source_type, kind=kind),
            auto_approve=True,
        )
    assert (outcome_new, new.status) == ("created", "candidate")
    assert merged.id == pending.id
    assert (outcome_merged, merged.status) == ("merged", "candidate")
    assert merged.statement == "Pending wording." and merged.strength == 0.4


@pytest.mark.parametrize("first_source,first_kind", [
    ("upwork_contract", "project"),
    ("client_feedback", "outcome"),
    ("chatgpt_user_turn", "metric"),
])
@pytest.mark.asyncio
async def test_trusted_promotion_drops_untrusted_or_client_ranking_fields(db_session, test_user, first_source, first_kind):
    """Approving a candidate via a trusted match takes tags/strength/origin from the trusted candidate only."""
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=unit(0))):
        first, outcome = await upsert_candidate_outcome(
            db_session, test_user.id,
            _cand("Ran the Kubernetes platform.", strength=1.0, skills=["Kubernetes"], industries=["Fintech"],
                  job_types=["cloud"], source_type=first_source, kind=first_kind, source_ref="c1"),
        )
    assert (outcome, first.status) == ("created", "candidate")
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=blend(0, 1, 0.95))):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id,
            _cand("Ran the platform on Azure.", strength=0.3, skills=["Azure"], source_type="bio_memory",
                  kind="project", source_ref="m9"),
            auto_approve=True,
        )
    assert fact.id == first.id
    assert (outcome, fact.status) == ("auto_approved", "approved")
    assert fact.strength == 0.3
    assert fact.skills == ["Azure"] and fact.industries == [] and fact.job_types == []
    assert (fact.source_type, fact.source_ref) == ("bio_memory", "m9")
    assert [s["source_type"] for s in fact.sources] == [first_source, "bio_memory"]


@pytest.mark.asyncio
async def test_changed_number_is_not_merged_into_approved_fact(db_session, test_user):
    """'160 servers' must not vanish into an approved '120 servers' fact: it goes to review."""
    existing = await _seed(db_session, test_user.id, "Migrated 120 servers to Azure.", unit(0),
                           status="approved")
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=blend(0, 1, 0.97))):
        fact, outcome = await upsert_candidate_outcome(
            db_session, test_user.id, _cand("Migrated 160 servers to Azure."))
    assert outcome == "created"
    assert fact.id != existing.id and fact.status == "candidate"
    assert fact.statement == "Migrated 160 servers to Azure."
    assert existing.statement == "Migrated 120 servers to Azure."
    assert await _count(db_session) == 2


@pytest.mark.asyncio
async def test_same_numbers_still_merge(db_session, test_user):
    existing = await _seed(db_session, test_user.id, "Migrated 160 servers to Azure in 2019.", unit(0),
                           status="approved")
    with patch("app.services.facts.generate_embedding", AsyncMock(return_value=blend(0, 1, 0.97))):
        fact, _ = await upsert_candidate_outcome(
            db_session, test_user.id, _cand("Moved 160 servers into Azure (2019)."))
    assert fact.id == existing.id
