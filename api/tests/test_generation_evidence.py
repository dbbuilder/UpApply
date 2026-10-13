"""Generation v2 step 2: rerank, per-need selection, anchor floor, voice samples."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.generation.brief import JobBrief
from app.services.generation import evidence as ev
from app.services.generation.evidence import (
    Evidence,
    _select_facts,
    format_facts,
    rerank_score,
    select_evidence,
)


def _fact(fid, strength=0.5, used=0, won=0, detail=None):
    return SimpleNamespace(
        id=fid, kind="project", statement=f"statement {fid}", detail=detail,
        strength=strength, times_used=used, times_in_won=won,
    )


def _brief(needs):
    return JobBrief(
        needs=needs, job_types=["sql"], client_signals={}, mirror_phrases=[],
        explicit_asks=[], questions=[],
    )


def test_rerank_score_formula():
    assert rerank_score(1.0, 1.0, 0, 0) == pytest.approx(0.9)
    assert rerank_score(0.5, 0.0, 8, 8) == pytest.approx(0.275 + 0.20 * 0.9)


def test_rerank_prefers_facts_that_win():
    unproven = rerank_score(0.8, 0.5, 10, 0)
    fresh = rerank_score(0.8, 0.5, 0, 0)
    winner = rerank_score(0.8, 0.5, 10, 8)
    assert unproven < fresh < winner


def test_select_facts_one_per_need_then_fill_dedup():
    a, b, c = _fact("a", 0.9), _fact("b", 0.5), _fact("c", 0.8)
    chosen = _select_facts([[(a, 0.9), (b, 0.8)], [(a, 0.85), (c, 0.7)]])
    assert [f.id for f in chosen] == ["a", "c", "b"]


def test_select_facts_caps_at_eight():
    per_need = [[(_fact(f"{n}-{i}", 0.9), 0.95) for i in range(8)] for n in range(3)]
    assert len(_select_facts(per_need)) == 8


def test_select_facts_fills_to_minimum_even_when_weak():
    weak = [(_fact(f"w{i}", 0.0, used=20), 0.1) for i in range(6)]
    assert len(_select_facts([weak])) == 4


def test_format_facts_includes_id_kind_and_detail():
    text = format_facts([_fact("f1", detail="more context")])
    assert "[f1] (project) statement f1" in text
    assert "more context" in text
    assert format_facts([]) == "(no approved facts matched this job)"


@pytest.mark.asyncio
async def test_select_evidence_covers_needs_adds_anchor_floor_and_voice():
    a, b, c, anchor = _fact("a", 0.9), _fact("b", 0.5), _fact("c", 0.8), _fact("anchor", 0.7)
    results = {1.0: [(a, 0.9), (b, 0.8)], 2.0: [(a, 0.85), (c, 0.7)], 3.0: [(anchor, 0.81)]}

    async def fake_search(db, user_id, query_embedding, limit=8, status="approved"):
        return results[query_embedding[0]][:limit]

    voice = [SimpleNamespace(id="p1", cover_letter_text="real letter")]
    embed = AsyncMock(side_effect=[[[1.0], [2.0], [3.0]], [[4.0]]])
    with patch.object(ev, "generate_embeddings_batch", embed), \
         patch.object(ev, "search_facts", AsyncMock(side_effect=fake_search)), \
         patch.object(ev, "_find_voice_samples", AsyncMock(return_value=voice)) as find_voice:
        result = await select_evidence(
            db=None, user_id="u1", brief=_brief(["need one", "need two"]),
            anchors={"always_include": ["160-server migration"], "sql": "ignored here"},
        )
    assert embed.call_args_list[0].args[0] == ["need one", "need two", "160-server migration"]
    assert embed.call_args_list[1].args[0] == ["need one\nneed two"]
    assert [f.id for f in result.facts] == ["a", "c", "b", "anchor"]
    assert result.voice_samples == voice
    assert find_voice.call_args.args[1] == "u1"
    assert find_voice.call_args.args[2] == [4.0]


@pytest.mark.asyncio
async def test_select_evidence_for_user_with_no_facts_or_proposals(db_session, test_user):
    """Review focus: a new user (empty facts table, no voice samples) gets empty evidence, not an error."""
    brief = JobBrief(
        needs=["need one", "need two"], job_types=[], client_signals={}, mirror_phrases=[],
        explicit_asks=[], questions=[], title="T", description="D",
    )
    vectors = [[1.0] + [0.0] * 1535, [0.0, 1.0] + [0.0] * 1534, [0.0, 0.0, 1.0] + [0.0] * 1533]
    with patch.object(ev, "generate_embeddings_batch", AsyncMock(return_value=vectors)):
        result = await select_evidence(db_session, test_user.id, brief, {"always_include": []})
    assert result.facts == []
    assert result.voice_samples == []
    assert format_facts(result.facts) == "(no approved facts matched this job)"


@pytest.mark.asyncio
async def test_select_evidence_voice_query_is_the_job_text_when_present():
    brief = JobBrief(
        needs=["need one"], job_types=[], client_signals={}, mirror_phrases=[],
        explicit_asks=[], questions=[], title="Azure lead", description="Migrate our SQL estate",
    )
    embed = AsyncMock(return_value=[[1.0], [2.0]])
    with patch.object(ev, "generate_embeddings_batch", embed), \
         patch.object(ev, "search_facts", AsyncMock(return_value=[])), \
         patch.object(ev, "_find_voice_samples", AsyncMock(return_value=[])):
        await select_evidence(None, "u1", brief, None)
    assert embed.call_args_list[0].args[0] == ["need one"]
    assert embed.call_args_list[1].args[0] == ["Azure lead\n\nMigrate our SQL estate"]


@pytest.mark.asyncio
async def test_select_evidence_skips_weak_anchor_match():
    a, anchor = _fact("a"), _fact("anchor")
    results = {1.0: [(a, 0.9)], 2.0: [(anchor, 0.5)]}

    async def fake_search(db, user_id, query_embedding, limit=8, status="approved"):
        return results[query_embedding[0]][:limit]

    with patch.object(ev, "generate_embeddings_batch", AsyncMock(return_value=[[1.0], [2.0], [3.0]])), \
         patch.object(ev, "search_facts", AsyncMock(side_effect=fake_search)), \
         patch.object(ev, "_find_voice_samples", AsyncMock(return_value=[])):
        result = await select_evidence(None, "u1", _brief(["only need"]), {"always_include": ["x"]})
    assert [f.id for f in result.facts] == ["a"]


@pytest.mark.asyncio
async def test_select_evidence_returns_empty_when_embeddings_fail():
    with patch.object(ev, "generate_embeddings_batch", AsyncMock(side_effect=RuntimeError("quota"))):
        result = await select_evidence(None, "u1", _brief(["need"]), None)
    assert result == Evidence()


def _vec(x, y=0.0):
    v = [0.0] * 1536
    v[0], v[1] = x, y
    return v


@pytest.mark.asyncio
async def test_find_voice_samples_filters_ai_and_weights_outcome(setup_database):
    from app.models.proposal import Proposal
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as db:
        user = User(email="voice-samples@example.com", hashed_password="x")
        db.add(user)
        await db.flush()
        db.add_all([
            Proposal(user_id=user.id, cover_letter_text="AI letter", author="ai", job_needs_embedding=_vec(1.0)),
            Proposal(user_id=user.id, cover_letter_text="Chris exact, no response", author="chris",
                     outcome="no_response", job_needs_embedding=_vec(1.0)),
            Proposal(user_id=user.id, cover_letter_text="Chris edited, hired", author="chris_edited_ai",
                     outcome="hired", job_needs_embedding=_vec(0.95, 0.31)),
            Proposal(user_id=user.id, cover_letter_text="Chris unrelated", author="chris",
                     job_needs_embedding=_vec(0.0, 1.0)),
        ])
        await db.flush()
        samples = await ev._find_voice_samples(db, user.id, _vec(1.0), limit=2)
        texts = [s.cover_letter_text for s in samples]  # read before rollback expires the rows
        await db.rollback()
    assert texts == ["Chris edited, hired", "Chris exact, no response"]


@pytest.mark.asyncio
async def test_voice_query_embedding_failure_only_loses_voice_samples():
    """An oversized job post must not take the needs/anchors embedding batch down with it."""
    a = _fact("a")
    brief = JobBrief(
        needs=["need one"], job_types=[], client_signals={}, mirror_phrases=[],
        explicit_asks=[], questions=[], title="T", description="x" * 50_000,
    )

    async def embed(texts):
        if any(len(t) > 10_000 for t in texts):
            raise RuntimeError("input too long")
        return [[1.0] for _ in texts]

    find_voice = AsyncMock(return_value=[SimpleNamespace(id="p1")])
    with patch.object(ev, "generate_embeddings_batch", AsyncMock(side_effect=embed)), \
         patch.object(ev, "search_facts", AsyncMock(return_value=[(a, 0.9)])), \
         patch.object(ev, "_find_voice_samples", find_voice):
        result = await select_evidence(None, "u1", brief, None)
    assert [f.id for f in result.facts] == ["a"]
    assert result.voice_samples == []
    find_voice.assert_not_called()


@pytest.mark.asyncio
async def test_select_evidence_forwards_excluded_proposals_to_voice_search():
    find_voice = AsyncMock(return_value=[])
    with patch.object(ev, "generate_embeddings_batch", AsyncMock(side_effect=lambda t: [[1.0] for _ in t])), \
         patch.object(ev, "search_facts", AsyncMock(return_value=[])), \
         patch.object(ev, "_find_voice_samples", find_voice):
        await select_evidence(None, "u1", _brief(["need"]), None, exclude_proposal_ids=["p-123"])
    assert find_voice.call_args.kwargs["exclude_ids"] == ["p-123"]


@pytest.mark.asyncio
async def test_find_voice_samples_excludes_by_id_or_upwork_proposal_id(setup_database):
    from app.models.proposal import Proposal
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as db:
        user = User(email="voice-exclude@example.com", hashed_password="x")
        db.add(user)
        await db.flush()
        golden = Proposal(user_id=user.id, cover_letter_text="Golden answer key", author="chris",
                          upwork_proposal_id="up-golden", job_needs_embedding=_vec(1.0))
        by_id = Proposal(user_id=user.id, cover_letter_text="Excluded by id", author="chris",
                         job_needs_embedding=_vec(1.0))
        other = Proposal(user_id=user.id, cover_letter_text="Other job", author="chris",
                         job_needs_embedding=_vec(0.9, 0.4))
        db.add_all([golden, by_id, other])
        await db.flush()
        samples = await ev._find_voice_samples(db, user.id, _vec(1.0), exclude_ids=["up-golden", by_id.id])
        texts = [s.cover_letter_text for s in samples]
        await db.rollback()
    assert texts == ["Other job"]
