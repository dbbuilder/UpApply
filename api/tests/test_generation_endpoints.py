"""API: generation_v2 flag routes cover letter (and screening) generation to the v2 engine."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.services.generation.brief import JobBrief
from app.services.generation.evidence import Evidence
from app.services.generation.orchestrator import GenerationResult
from app.services.generation.writer import Draft
from app.services.job_analysis import AnalysisResult
from tests.conftest import test_engine

JOB_DATA = {
    "upwork_url": "https://www.upwork.com/jobs/~01v2engine",
    "title": "Azure SQL migration",
    "description": "Move our SQL Server estate to Azure with a zero downtime cutover.",
    "skills_required": ["SQL Server", "Azure"],
}
WARNING = "Length 8 words is outside the 200-350 target for this job."
FACT_USED = SimpleNamespace(id="fact-1", statement="Led a 160-server on-prem to Azure migration.")
FACT_UNUSED = SimpleNamespace(id="fact-2", statement="Unused fact.")


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        match_score=82.0, skill_matches=[], missing_skills=[], strengths=[], concerns=[],
        deal_breaker_warnings=[], relevant_memories=[], recommendation="Good match - consider applying",
    )


def _result(questions):
    brief = JobBrief(
        needs=["Has migrated SQL Server to Azure"], job_types=["sql"],
        client_signals={"complexity": "standard"}, mirror_phrases=[], explicit_asks=[],
        questions=questions, title=JOB_DATA["title"], description=JOB_DATA["description"],
    )
    draft = Draft(
        cover_letter="Your cutover is the hard part.\n\nWarm regards,",
        screening_answers=[{"question": q, "answer": f"Answer to {q}"} for q in questions],
        fact_ids_used=["fact-1"],
    )
    evidence = Evidence(facts=[FACT_USED, FACT_UNUSED], voice_samples=[SimpleNamespace(id="prop-1")])
    return GenerationResult(draft=draft, brief=brief, evidence=evidence, warnings=[WARNING])


async def _enable_v2():
    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE user_profiles SET generation_v2 = true"))


@pytest.mark.asyncio
async def test_cover_letter_generate_routes_to_v2_when_flag_on(client: AsyncClient, auth_headers_with_profile):
    await _enable_v2()
    question = "Describe a similar migration."
    engine = AsyncMock(return_value=_result([question]))
    with patch("app.api.v1.jobs.run_full_analysis", AsyncMock(return_value=_analysis())), \
         patch("app.api.v1.jobs.generate_embedding", AsyncMock(side_effect=RuntimeError("no quota"))), \
         patch("app.api.v1.jobs.generate_application", engine), \
         patch("app.api.v1.jobs.generate_cover_letter", AsyncMock()) as legacy:
        resp = await client.post(
            "/api/v1/jobs/cover-letters/generate",
            headers=auth_headers_with_profile,
            json={
                "job_data": JOB_DATA,
                "screening_questions": [question],
                "prototype_url": "https://demo.example.com",
                "include_call_offer": False,
                "custom_instructions": "mention fixed fee",
            },
        )
    assert resp.status_code == 200, resp.text
    legacy.assert_not_called()
    kwargs = engine.call_args.kwargs
    assert kwargs["title"] == JOB_DATA["title"]
    assert kwargs["description"] == JOB_DATA["description"]
    assert kwargs["skills"] == JOB_DATA["skills_required"]
    assert kwargs["questions"] == [question]
    assert kwargs["include_call_offer"] is False
    assert kwargs["prototype_url"] == "https://demo.example.com"
    assert kwargs["extra_points"] == "mention fixed fee"

    body = resp.json()
    assert body["content"] == "Your cutover is the hard part.\n\nWarm regards,"
    assert body["model_used"] == settings.cover_letter_model
    assert body["word_count"] == 8
    assert body["screening_answers"] == [{"question": question, "answer": f"Answer to {question}"}]
    assert body["verify_warnings"] == [WARNING]
    assert body["facts_used"] == [{"id": "fact-1", "statement": FACT_USED.statement}]

    async with test_engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT brief, fact_ids_used, voice_sample_ids, verify_warnings, prompt_version "
                 "FROM cover_letters WHERE id = :id"),
            {"id": body["id"]},
        )).one()
    assert row.brief["needs"] == ["Has migrated SQL Server to Azure"]
    assert row.fact_ids_used == ["fact-1"]
    assert row.voice_sample_ids == ["prop-1"]
    assert row.verify_warnings == [WARNING]
    assert row.prompt_version == "v2"


@pytest.mark.asyncio
async def test_cover_letter_generate_keeps_legacy_path_when_flag_off(client: AsyncClient, auth_headers_with_profile):
    engine = AsyncMock()
    with patch("app.api.v1.jobs.run_full_analysis", AsyncMock(return_value=_analysis())), \
         patch("app.api.v1.jobs.generate_embedding", AsyncMock(side_effect=RuntimeError("no quota"))), \
         patch("app.api.v1.jobs.find_relevant_proposals", AsyncMock(return_value=[])), \
         patch("app.api.v1.jobs.generate_cover_letter", AsyncMock(return_value="Legacy letter.")), \
         patch("app.api.v1.jobs.generate_application", engine):
        resp = await client.post(
            "/api/v1/jobs/cover-letters/generate",
            headers=auth_headers_with_profile,
            json={"job_data": JOB_DATA, "screening_questions": ["Q?"]},
        )
    assert resp.status_code == 200, resp.text
    engine.assert_not_called()
    body = resp.json()
    assert body["content"] == "Legacy letter."
    assert body["model_used"] == settings.legacy_cover_letter_model
    assert body["screening_answers"] is None
    assert body["verify_warnings"] is None
    assert body["facts_used"] is None


@pytest.mark.asyncio
async def test_cover_letter_generate_v2_without_screening_questions(client: AsyncClient, auth_headers_with_profile):
    """Review focus: most posts have no screening questions; the field is simply omitted."""
    await _enable_v2()
    engine = AsyncMock(return_value=_result([]))
    with patch("app.api.v1.jobs.run_full_analysis", AsyncMock(return_value=_analysis())), \
         patch("app.api.v1.jobs.generate_embedding", AsyncMock(side_effect=RuntimeError("no quota"))), \
         patch("app.api.v1.jobs.generate_application", engine):
        resp = await client.post(
            "/api/v1/jobs/cover-letters/generate",
            headers=auth_headers_with_profile,
            json={"job_data": JOB_DATA},
        )
    assert resp.status_code == 200, resp.text
    assert engine.call_args.kwargs["questions"] == []
    assert resp.json()["screening_answers"] == []


@pytest.mark.asyncio
async def test_cover_letter_generate_v2_llm_failure_is_502_and_saves_nothing(client: AsyncClient, auth_headers_with_profile):
    """Review focus: invalid/partial JSON or a proxy that strips output_config surfaces as LLMError."""
    from app.services.llm import LLMError

    await _enable_v2()
    engine = AsyncMock(side_effect=LLMError("structured_call returned invalid JSON"))
    with patch("app.api.v1.jobs.run_full_analysis", AsyncMock(return_value=_analysis())), \
         patch("app.api.v1.jobs.generate_embedding", AsyncMock(side_effect=RuntimeError("no quota"))), \
         patch("app.api.v1.jobs.generate_application", engine):
        resp = await client.post(
            "/api/v1/jobs/cover-letters/generate",
            headers=auth_headers_with_profile,
            json={"job_data": JOB_DATA},
        )
    assert resp.status_code == 502
    assert "invalid JSON" in resp.json()["detail"]
    async with test_engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM cover_letters"))).scalar_one()
    assert count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [
    {"screening_questions": ["q" * 2001]},
    {"screening_questions": ["Q?"] * 21},
    {"custom_instructions": "x" * 2001},
    {"prototype_url": "https://example.com/" + "a" * 500},
    {"prototype_url": "javascript:alert(1)"},
    {"prototype_url": "demo.example.com"},
    {"job_data": {**JOB_DATA, "title": "t" * 301}},
    {"job_data": {**JOB_DATA, "description": "d" * 20001}},
    {"job_data": {**JOB_DATA, "skills_required": ["s"] * 51}},
    {"job_data": {**JOB_DATA, "skills_required": ["s" * 201]}},
])
async def test_cover_letter_generate_rejects_oversized_or_bad_input(
    client: AsyncClient, auth_headers_with_profile, override
):
    engine = AsyncMock()
    with patch("app.api.v1.jobs.generate_application", engine), \
         patch("app.api.v1.jobs.generate_cover_letter", AsyncMock()) as legacy:
        resp = await client.post(
            "/api/v1/jobs/cover-letters/generate",
            headers=auth_headers_with_profile,
            json={"job_data": JOB_DATA, **override},
        )
    assert resp.status_code == 422, resp.text
    engine.assert_not_called()
    legacy.assert_not_called()


@pytest.mark.asyncio
async def test_screening_generate_routes_to_v2_when_flag_on(client: AsyncClient, auth_headers_with_profile):
    await _enable_v2()
    question = "How would you handle the cutover?"
    engine = AsyncMock(return_value=_result([question]))
    with patch("app.api.v1.screening_answers.generate_application", engine):
        resp = await client.post(
            "/api/v1/screening-answers/generate",
            headers=auth_headers_with_profile,
            json={
                "question": question,
                "job_title": JOB_DATA["title"],
                "job_description": JOB_DATA["description"],
                "job_skills": JOB_DATA["skills_required"],
            },
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"answer": f"Answer to {question}", "verify_warnings": [WARNING]}
    kwargs = engine.call_args.kwargs
    assert kwargs["questions"] == [question]
    assert kwargs["title"] == JOB_DATA["title"]
    assert kwargs["description"] == JOB_DATA["description"]
    assert kwargs["skills"] == JOB_DATA["skills_required"]
    assert kwargs["brief"] is None
    assert kwargs["credit_usage"] is False
    assert kwargs["answers_only"] is True


@pytest.mark.asyncio
async def test_screening_generate_reuses_stored_brief_of_the_users_letter(client: AsyncClient, auth_headers_with_profile):
    await _enable_v2()
    letter_engine = AsyncMock(return_value=_result(["Describe a similar migration."]))
    with patch("app.api.v1.jobs.run_full_analysis", AsyncMock(return_value=_analysis())), \
         patch("app.api.v1.jobs.generate_embedding", AsyncMock(side_effect=RuntimeError("no quota"))), \
         patch("app.api.v1.jobs.generate_application", letter_engine):
        letter = await client.post(
            "/api/v1/jobs/cover-letters/generate",
            headers=auth_headers_with_profile,
            json={"job_data": JOB_DATA, "screening_questions": ["Describe a similar migration."]},
        )
    assert letter.status_code == 200, letter.text

    question = "How would you handle the cutover?"
    engine = AsyncMock(return_value=_result([question]))
    with patch("app.api.v1.screening_answers.generate_application", engine):
        resp = await client.post(
            "/api/v1/screening-answers/generate",
            headers=auth_headers_with_profile,
            json={"question": question, "cover_letter_id": letter.json()["id"]},
        )
    assert resp.status_code == 200, resp.text
    kwargs = engine.call_args.kwargs
    assert kwargs["credit_usage"] is False
    assert kwargs["brief"].needs == ["Has migrated SQL Server to Azure"]
    assert kwargs["brief"].questions == [question]
    assert kwargs["title"] == JOB_DATA["title"]


@pytest.mark.asyncio
async def test_screening_generate_keeps_legacy_path_when_flag_off(client: AsyncClient, auth_headers_with_profile):
    from unittest.mock import MagicMock

    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Legacy answer"))]
    ))
    engine = AsyncMock()
    with patch("app.api.v1.screening_answers.generate_application", engine), \
         patch("app.api.v1.screening_answers.generate_embedding", AsyncMock(side_effect=RuntimeError("no quota"))), \
         patch("app.api.v1.screening_answers.get_openai_client", return_value=openai_client):
        resp = await client.post(
            "/api/v1/screening-answers/generate",
            headers=auth_headers_with_profile,
            json={"question": "Why you?"},
        )
    assert resp.status_code == 200, resp.text
    engine.assert_not_called()
    assert resp.json() == {"answer": "Legacy answer", "verify_warnings": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [
    {"question": "q" * 2001},
    {"job_title": "t" * 301},
    {"job_description": "d" * 20001},
    {"job_skills": ["s"] * 51},
    {"job_skills": ["s" * 201]},
    {"cover_letter_id": "c" * 37},
])
async def test_screening_generate_rejects_oversized_input(client: AsyncClient, auth_headers_with_profile, override):
    await _enable_v2()
    engine = AsyncMock()
    with patch("app.api.v1.screening_answers.generate_application", engine):
        resp = await client.post(
            "/api/v1/screening-answers/generate",
            headers=auth_headers_with_profile,
            json={"question": "Why you?", **override},
        )
    assert resp.status_code == 422, resp.text
    engine.assert_not_called()
