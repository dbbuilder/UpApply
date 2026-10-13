"""Generation v2 orchestrator: verify, single repair pass, usage crediting."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.generation import generate_application
from app.services.generation import orchestrator as orch
from app.services.generation.brief import JobBrief
from app.services.generation.evidence import Evidence
from app.services.generation.verify import CLAIM_CHECK_SKIPPED
from app.services.generation.writer import Draft

SENTENCE = "Your migration plan needs a rollback path that was proven on a live estate."
CLEAN = " ".join([SENTENCE] * 17) + "\n\nWarm regards,"
DIRTY = "I have done this before. " + CLEAN
BRIEF = JobBrief(needs=["n"], job_types=[], client_signals={"complexity": "standard"},
                 mirror_phrases=[], explicit_asks=[], questions=[], title="T", description="D")
FACT = SimpleNamespace(id="fact-1", statement="s", kind="project", detail=None)
USER = SimpleNamespace(id="u1")
PROFILE = SimpleNamespace(preferred_closing=None, proposal_anchors={"always_include": []})


def _draft(text, fact_ids=("fact-1",)):
    return Draft(cover_letter=text, screening_answers=[], fact_ids_used=list(fact_ids))


async def _run(drafts, claims=None, evidence=None, **kwargs):
    db = AsyncMock()
    write = AsyncMock(side_effect=drafts)
    with patch.object(orch, "build_job_brief", AsyncMock(return_value=BRIEF)), \
         patch.object(orch, "select_evidence", AsyncMock(return_value=evidence or Evidence(facts=[FACT]))), \
         patch.object(orch, "write_application", write), \
         patch.object(orch, "check_claims", AsyncMock(return_value=claims or [])):
        result = await generate_application(
            db=db, user=USER, profile=PROFILE, title="T", description="D", skills=[], questions=[], **kwargs
        )
    return result, write, db


@pytest.mark.asyncio
async def test_clean_draft_needs_no_repair_and_credits_facts():
    result, write, db = await _run([_draft(CLEAN)])
    assert write.call_count == 1
    assert result.warnings == []
    assert result.draft.cover_letter == CLEAN
    stmt = str(db.execute.call_args.args[0])
    assert "UPDATE facts SET times_used" in stmt


@pytest.mark.asyncio
async def test_violation_triggers_exactly_one_repair_with_notes():
    result, write, _ = await _run([_draft(DIRTY), _draft(CLEAN)])
    assert write.call_count == 2
    notes = write.call_args_list[1].kwargs["repair_notes"]
    assert any('starts with "I"' in n for n in notes)
    assert result.warnings == []


@pytest.mark.asyncio
async def test_still_failing_after_repair_returns_warnings():
    result, write, _ = await _run([_draft(DIRTY), _draft(DIRTY)])
    assert write.call_count == 2
    assert any('starts with "I"' in w for w in result.warnings)


@pytest.mark.asyncio
async def test_claim_check_skip_marker_does_not_trigger_repair():
    result, write, _ = await _run([_draft(CLEAN)], claims=[CLAIM_CHECK_SKIPPED])
    assert write.call_count == 1
    assert result.warnings == [CLAIM_CHECK_SKIPPED]


@pytest.mark.asyncio
async def test_missing_prototype_url_is_repairable():
    result, write, _ = await _run(
        [_draft(CLEAN), _draft("See https://demo.example.com. " + CLEAN)],
        prototype_url="https://demo.example.com",
    )
    assert write.call_count == 2
    assert result.warnings == []


@pytest.mark.asyncio
async def test_reused_brief_skips_brief_call_and_credit_usage_false_skips_crediting():
    db = AsyncMock()
    build = AsyncMock(return_value=BRIEF)
    with patch.object(orch, "build_job_brief", build), \
         patch.object(orch, "select_evidence", AsyncMock(return_value=Evidence(facts=[FACT]))), \
         patch.object(orch, "write_application", AsyncMock(return_value=_draft(CLEAN))), \
         patch.object(orch, "check_claims", AsyncMock(return_value=[])):
        result = await generate_application(
            db=db, user=USER, profile=PROFILE, title="T", description="D", skills=[], questions=["Q?"],
            brief=BRIEF, credit_usage=False,
        )
    build.assert_not_called()
    assert result.brief is BRIEF
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_no_facts_warns_and_skips_crediting():
    result, _, db = await _run([_draft(CLEAN, fact_ids=())], evidence=Evidence())
    assert result.warnings == [orch.NO_FACTS_WARNING]
    db.execute.assert_not_called()
