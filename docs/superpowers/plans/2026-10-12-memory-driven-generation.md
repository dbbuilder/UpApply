# Memory-Driven Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Run every task test-first, exactly as written. Stop on any unexpected failure and explain it before you change anything.

**Goal:** Make UpApply's cover letters and screening answers as specific and as much in Chris's voice as the ChatGPT workflow that has been winning work, then improve on it by learning from outcomes. Every claim in a draft must trace to a verified fact. What Chris actually submits must flow back into the system.

**Architecture:** The work ships as four stacked branches, one per phase:

| Phase | Branch | What it does |
|---|---|---|
| 0 | `feat/mdg-0-bleeding` from `main` | Fixes the crash and data-quality bugs and redacts the leaked secrets. |
| 1 | `feat/mdg-1-knowledge` | Adds the knowledge layer: a new `facts` table, `proposals` repurposed as voice samples, and the ingestion and review UI. |
| 2 | `feat/mdg-2-engine` | Adds the generation v2 engine behind the per-user `generation_v2` flag. Each draft runs brief → evidence → write → verify, with at most one repair. |
| 3 | `feat/mdg-3-loop` | Adds the refine thread, Submit-click capture and outcome sync. Wins credit the facts they used. |

Alembic migrations chain `021_global_signal_pool` (the current head) → `022_knowledge_layer` → `023_generation_v2` → `024_refine_loop`. The legacy generation path stays in place, unchanged, until the flag is on and the golden-set eval passes.

**Tech Stack:**
- API: FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16 with pgvector (HNSW, cosine), pytest and pytest-asyncio.
- Models and SDKs: Anthropic Python SDK (structured outputs via `output_config`), OpenAI `text-embedding-3-small` (1536-d).
- Extension: Chrome MV3 with React, TypeScript, Vite and zustand; Vitest and jsdom are new in Phase 3.

**Spec:** `/Users/admin/dev2/UpApply/docs/superpowers/specs/2026-10-12-memory-driven-generation-design.md`

**Tasks:** 39 in total (Phase 0: 6, Phase 1: 12, Phase 2: 11, Phase 3: 10).

---

## Global Constraints

These values are fixed by the spec. Do not change them without a spec change.

**Models.** All model IDs live in `api/app/core/config.py`, so they can be changed in config without code changes.

| Step | Setting | Value |
|---|---|---|
| Writer and refine thread | `cover_letter_model` | `claude-opus-5-5`, at `writer_effort = "high"` (set explicitly, because 5.5 defaults to `medium`) |
| Job brief, claim check, fact extraction | `extraction_model` | `claude-haiku-4-5` |
| Legacy flag-off path | `legacy_cover_letter_model` | `claude-sonnet-4-6` (this path still passes `temperature`) |
| Embeddings | (unchanged) | `text-embedding-3-small`, 1536 dimensions |

**Opus 5.5 request shape.**
- Never send `temperature`, `thinking`, `budget_tokens` or assistant prefill.
- Never force `tool_choice` (`any` or `tool`). The refine thread uses `tool_choice: {"type": "auto"}`.
- Response shape comes from `output_config.format` (JSON schema). Depth comes from `output_config.effort`.
- Haiku calls never send `effort`.

**Facts, dedupe and evidence selection.**
- Dedupe and auto-approve threshold: cosine similarity **≥ 0.92**. A candidate that matches an approved fact is merged and stays approved. A candidate that matches nothing goes to review. A rejected fact stays rejected.
- Only `status='approved'` facts can be retrieved.
- Rerank score: **0.55·similarity + 0.25·strength + 0.20·win_signal**, where `win_signal = (times_in_won + 1) / (times_used + 2)`.
- The brief has **3-6 needs**. Each need retrieves its top-8 approved facts.
- Select **4-8 facts** in total, with **≥1 per need** where one is available, de-duplicated across needs.
- The `always_include` anchors are added beyond the 8-fact cap when their nearest approved fact has similarity ≥ 0.75.
- Use **2-3 voice samples**, with `author ∈ {chris, chris_edited_ai}`, matched job↔job on `job_needs_embedding` and weighted by outcome.

**Writing rules.** These are hard rules: `check_rules` enforces them and a violation triggers the one repair pass.
- No sentence may begin with "I".
- No salutation (Hello, Hi, Hey, Dear, Greetings or Subject).
- The letter ends with `Warm regards,` followed by `preferred_closing`. Code appends this closing; the model never writes it.
- None of the 14 `BANNED_PHRASES` may appear. The list is `api/app/services/cover_letter.py` and mirrors the legacy prompt.
- Letter length depends on the job: terse posts 150-250 words, standard 200-350, complex 300-450, with ±10% slack. Screening answers are 2-5 sentences.
- No fact, no claim: every specific must map to a provided fact. The claim check flags anything else.
- The call offer and the prototype URL are woven in by the model, not appended.

**Pipeline limits.**
- Verify allows at most **one** automatic repair pass. A `CLAIM_CHECK_SKIPPED` warning on its own never triggers a repair.
- Refine endpoint rate limit: **30/hour**. The refine tool loop runs at most 4 rounds.
- No-response rule: a proposal with no signal **14 days** after submission becomes `no_response`.
- Outcomes only move forward. Facts get `times_in_won` credit once per proposal, on its first `replied`, `interviewed` or `hired`.
- Submit capture sets `author = chris` when ≥ 90% of words changed (`CHRIS_REWRITE_THRESHOLD = 0.9`), and `chris_edited_ai` otherwise.

**Eval pass bar (spec §4.2).**
- Use 15-20 golden jobs.
- The new letter must be preferred in **≥ 75%** of the blind pairs; ties count against the new letter.
- There must be zero `Unsupported claim` warnings.
- Every new draft must cite ≥ 2 facts.

**Data safety.**
- **Nothing is deleted from the database at any stage.** Corpus memories are flagged (`exclude_from_retrieval`) and ChatGPT-imported proposals are re-tagged (`author='ai'`).
- Migrations only add columns and tables. A downgrade drops only what its own upgrade added.
- IDs are `String(36)` UUID strings, as everywhere else in the repo. Compare fact and proposal IDs with `str(...)`.

**No deploys.** The implementing agent never does any of the following. Each of them is a Human Handoff at the end of this plan.
- Push or open PRs.
- Run migrations against prod or staging.
- Edit Doppler or Render env vars.
- Flip `generation_v2` in prod.
- Run the ingestion or eval scripts against prod.

**Commit hygiene.**
- Stage only the paths named in each task. Never use `git add -A` or `git commit -a`. The working tree holds unrelated uncommitted and untracked files.
- Every commit ends with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

**Test command.** Unit tests that do not touch the database can drop the `TEST_DATABASE_URL` prefix.

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q <target>
```

---

## Review Focus

These are the five input classes most likely to break in production without anyone noticing. Each one has a test in the task that owns the behaviour. Reviewers should confirm that these tests exist, fail before the change and pass after it.

1. **A job post with no screening questions.** Most posts have none.
   - Task 2.6 `test_writer_job_with_no_screening_questions_returns_no_answers`: the prompt says "none", and stray model answers are dropped.
   - Task 2.8 `test_cover_letter_generate_v2_without_screening_questions`: the request omits the field, the engine gets `questions=[]` and the response has `screening_answers == []`.
   - Task 3.8 `returns no answers on a job without screening questions`.
2. **A user with an empty `facts` table and no voice samples.** This is a new user, or Chris before he finishes reviewing facts.
   - Task 2.4 `test_select_evidence_for_user_with_no_facts_or_proposals` runs on a real database: evidence comes back empty, with no error.
   - Task 2.7 `test_no_facts_warns_and_skips_crediting`: the response carries `NO_FACTS_WARNING` and no `times_used` update runs.
3. **The Upwork cover-letter textarea is missing or empty when Submit is clicked.** Upwork's DOM drifts.
   - Task 3.8 `returns null cover letter when the textarea is empty or missing`.
   - Task 3.9 `handleSubmitClick` returns before messaging the background when `coverLetter` is null, so `PUT /final` is never called with empty text.
4. **The LLM returns invalid or partial JSON.**
   - Task 1.2 `test_structured_call_raises_on_invalid_json` and `test_structured_call_raises_on_bad_stop` (`max_tokens` truncation) both raise `LLMError`.
   - Task 2.8 `test_cover_letter_generate_v2_llm_failure_is_502_and_saves_nothing` returns 502 and writes no row.
   - Task 3.2 `test_invalid_or_partial_json_raises_refine_error` covers non-JSON, valid JSON missing required keys, and truncated JSON.
5. **The proxy strips or rejects `output_config`.** This is the AICostCentral `ANTHROPIC_BASE_URL`.
   - Task 1.2 `test_structured_call_prose_reply_names_the_proxy` covers the stripped case: the reply is prose, and the `LLMError` names `output_config`.
   - Task 1.2 `test_structured_call_wraps_api_errors` covers the rejected case: HTTP 400 becomes `LLMError`, which the endpoints turn into 502.
   - Task 3.2 `test_proxy_rejecting_request_raises_refine_error`: the refine call (`tools` plus `output_config`) maps an API error to `RefineError`, then 502.

---

## Phase 0: Stop the bleeding

Fix the crash and data-quality bugs listed in the spec's sub-project 0 so the current pipeline stops failing quietly. Then remove the leaked credentials from the working tree. The phase covers five code fixes, each with its own regression test: the screening-answer 500, the two queue background tasks that call `run_full_analysis` with the wrong kwargs, `model_used` mislabelling, declined letters used as voice examples, and the `winning_proposal_to_memory` TypeError. A sixth hygiene task redacts the plaintext password and the partial API key. Phase 0 adds no schema, no new services and no extension code. It ships as one small PR from `main`, ahead of every other phase. Every test below was run against the current code and fails for the stated reason. After the fixes the full suite goes from 191 to 202 passing.

**Branch:** `feat/mdg-0-bleeding` (from `main`; `main` is `feat/memory-driven-generation` minus the spec commit only)

```bash
cd /Users/admin/dev2/UpApply
git switch -c feat/mdg-0-bleeding main
```

The working tree holds unrelated uncommitted changes (`extension/package*.json`, `extension/public/manifest.json`) and many untracked files. Every commit below stages **only** the named paths. Never use `git add -A` or `git commit -a`.

Test command used throughout (abbreviated `PYTEST` below):

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q
```

---

### Task 0.1: Screening-answer generate 500s when job context is sent

The handler in `api/app/api/v1/screening_answers.py` checks the job context on `body.` and then reads it from `request.`, which is the Starlette `Request` object. That raises `AttributeError: 'Request' object has no attribute 'job_title'`.

**Files:**
- Create: `api/tests/test_screening_generate.py`
- Modify: `api/app/api/v1/screening_answers.py:296,298,300` (inside `generate_screening_answer`, lines 241-330)

**Interfaces:**
- Consumes: `POST /api/v1/screening-answers/generate` with `ScreeningAnswerGenerateRequest(question, job_title?, job_description?, job_skills?)` (defined at `screening_answers.py:26-30`); module-level names `generate_embedding` and `get_openai_client` (patched in the test).
- Produces: unchanged response `ScreeningAnswerGenerateResponse(answer: str)`.

- [ ] **Step 1: Write the failing test** at `/Users/admin/dev2/UpApply/api/tests/test_screening_generate.py`

```python
"""Regression: POST /screening-answers/generate with job context (phase 0)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


def _mock_openai(answer: str = "Built three of these for fintech clients."):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = answer
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_generate_with_job_context_includes_context_in_prompt(
    client: AsyncClient, auth_headers_with_profile: dict
):
    openai_client = _mock_openai()
    with patch(
        "app.api.v1.screening_answers.generate_embedding",
        AsyncMock(return_value=[0.1] * 1536),
    ), patch(
        "app.api.v1.screening_answers.get_openai_client",
        return_value=openai_client,
    ):
        r = await client.post(
            "/api/v1/screening-answers/generate",
            headers=auth_headers_with_profile,
            json={
                "question": "Describe your recent experience with similar projects",
                "job_title": "FastAPI pgvector search build",
                "job_description": "We need semantic search over 2M support tickets.",
                "job_skills": ["Python", "PostgreSQL", "pgvector"],
            },
        )

    assert r.status_code == 200
    assert r.json()["answer"] == "Built three of these for fintech clients."
    user_prompt = openai_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "Job: FastAPI pgvector search build" in user_prompt
    assert "Required skills: Python, PostgreSQL, pgvector" in user_prompt
    assert "Description excerpt: We need semantic search over 2M support tickets." in user_prompt


@pytest.mark.asyncio
async def test_generate_without_job_context_still_works(
    client: AsyncClient, auth_headers_with_profile: dict
):
    openai_client = _mock_openai("Available 30 hrs/week.")
    with patch(
        "app.api.v1.screening_answers.generate_embedding",
        AsyncMock(return_value=[0.1] * 1536),
    ), patch(
        "app.api.v1.screening_answers.get_openai_client",
        return_value=openai_client,
    ):
        r = await client.post(
            "/api/v1/screening-answers/generate",
            headers=auth_headers_with_profile,
            json={"question": "What is your availability?"},
        )

    assert r.status_code == 200
    user_prompt = openai_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "JOB CONTEXT" not in user_prompt
```

- [ ] **Step 2: Run and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_screening_generate.py
```

Expected: `1 failed, 1 passed`. The failure is in `test_generate_with_job_context_includes_context_in_prompt` with `AttributeError: 'Request' object has no attribute 'job_title'`.

- [ ] **Step 3: Implement.** In `/Users/admin/dev2/UpApply/api/app/api/v1/screening_answers.py`, replace lines 295-300:

```python
    if body.job_title:
        job_ctx_parts.append(f"Job: {request.job_title}")
    if body.job_skills:
        job_ctx_parts.append(f"Required skills: {', '.join(request.job_skills[:10])}")
    if body.job_description:
        job_ctx_parts.append(f"Description excerpt: {request.job_description[:400]}")
```

with:

```python
    if body.job_title:
        job_ctx_parts.append(f"Job: {body.job_title}")
    if body.job_skills:
        job_ctx_parts.append(f"Required skills: {', '.join(body.job_skills[:10])}")
    if body.job_description:
        job_ctx_parts.append(f"Description excerpt: {body.job_description[:400]}")
```

(`request: Request` stays in the signature. slowapi's `@limiter.limit` needs it.)

- [ ] **Step 4: Run and confirm it passes**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_screening_generate.py
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/api/v1/screening_answers.py api/tests/test_screening_generate.py
git commit -m "$(cat <<'EOF'
fix(screening): read job context from body, not Request, in generate

POST /screening-answers/generate raised AttributeError (500) whenever
job_title/job_skills/job_description were sent, because the prompt
builder read them from the Starlette Request instead of the body.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 0.2: Queue background tasks call `run_full_analysis` with nonexistent kwargs

`run_full_analysis` (`api/app/services/job_analysis.py:605-616`) takes `db, user_id, profile, job_description, job_skills, job_title="", budget_amount=None, budget_min=None, client_info=None, precomputed_embedding=None`. Both background tasks in `job_queue.py` pass `title=`, `description=`, `skills=` and `budget=`, and omit `user_id`. The resulting `TypeError` is swallowed by each task's `except Exception`. Queue drafts silently reset to `draft_status="none"`, and "score anyway" never scores. The spec names the draft call (`:381-389`). The identical call in `_score_pre_filtered_background` (`:665-673`) has the same bug, so this task fixes both.

**Files:**
- Create: `api/tests/test_job_queue_background.py`
- Modify: `api/app/api/v1/job_queue.py:381-389` (`_generate_draft_background`) and `api/app/api/v1/job_queue.py:665-673` (`_score_pre_filtered_background`)

**Interfaces:**
- Consumes: `run_full_analysis(db, user_id, profile, job_description, job_skills, job_title="", budget_amount=None, budget_min=None, client_info=None, precomputed_embedding=None) -> AnalysisResult`; `JobQueueItem` fields `title, description, skills, budget_amount, client_info`.
- Produces: no signature changes. `_generate_draft_background(item_id: str, user_id: str) -> None` and `_score_pre_filtered_background(item_id: str, user_id: str) -> None` now succeed.

- [ ] **Step 1: Write the failing test** at `/Users/admin/dev2/UpApply/api/tests/test_job_queue_background.py`. `autospec=True` makes the mock enforce the real signature, so a kwargs mismatch raises `TypeError` exactly as in production.

```python
"""Regression: job-queue background tasks call run_full_analysis with its real signature (phase 0)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1 import job_queue
from app.services.job_analysis import AnalysisResult


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        match_score=82.0,
        skill_matches=[],
        missing_skills=["Rust"],
        strengths=["Deep PostgreSQL background"],
        concerns=[],
        deal_breaker_warnings=[],
        relevant_memories=[],
        recommendation="Excellent match - highly recommended to apply",
    )


def _item():
    return SimpleNamespace(
        id="item-1",
        title="Postgres tuning for SaaS",
        description="Slow queries on a 400GB database.",
        skills=["PostgreSQL", "Python"],
        budget_amount="$2,000",
        client_info={"location": "United States"},
        draft_cover_letter=None,
        draft_status="generating",
        draft_generated_at=None,
        ai_score=None,
        ai_reasoning=None,
    )


def _session_maker(item):
    result = MagicMock()
    result.scalar_one_or_none.return_value = item
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    maker = MagicMock()
    maker.return_value.__aenter__.return_value = db
    maker.return_value.__aexit__.return_value = False
    return maker, db


def _assert_called_with_real_signature(mock_rfa, db, profile, item):
    mock_rfa.assert_awaited_once()
    kwargs = mock_rfa.call_args.kwargs
    assert kwargs["db"] is db
    assert kwargs["user_id"] == "user-1"
    assert kwargs["profile"] is profile
    assert kwargs["job_description"] == item.description
    assert kwargs["job_skills"] == item.skills
    assert kwargs["job_title"] == item.title
    assert kwargs["budget_amount"] == item.budget_amount
    assert kwargs["client_info"] == item.client_info


@pytest.mark.asyncio
async def test_generate_draft_background_produces_ready_draft():
    item = _item()
    profile = MagicMock()
    maker, db = _session_maker(item)

    with patch("app.core.database.async_session_maker", maker), \
         patch.object(job_queue, "_get_user_profile", AsyncMock(return_value=profile)), \
         patch.object(job_queue, "_record_outcome", AsyncMock()), \
         patch.object(job_queue, "record_proposal_drafted", AsyncMock()), \
         patch("app.services.job_analysis.run_full_analysis", autospec=True) as mock_rfa, \
         patch("app.services.job_analysis.find_relevant_proposals", AsyncMock(return_value=[])), \
         patch("app.services.cover_letter.generate_cover_letter", AsyncMock(return_value="Draft body")):
        mock_rfa.return_value = _analysis()
        await job_queue._generate_draft_background(item_id="item-1", user_id="user-1")

    _assert_called_with_real_signature(mock_rfa, db, profile, item)
    assert item.draft_status == "ready"
    assert item.draft_cover_letter == "Draft body"


@pytest.mark.asyncio
async def test_score_pre_filtered_background_sets_score():
    item = _item()
    profile = MagicMock()
    maker, db = _session_maker(item)

    with patch("app.core.database.async_session_maker", maker), \
         patch.object(job_queue, "_get_user_profile", AsyncMock(return_value=profile)), \
         patch("app.services.job_analysis.run_full_analysis", autospec=True) as mock_rfa:
        mock_rfa.return_value = _analysis()
        await job_queue._score_pre_filtered_background(item_id="item-1", user_id="user-1")

    _assert_called_with_real_signature(mock_rfa, db, profile, item)
    assert item.ai_score == 82.0
    assert "Missing: Rust." in item.ai_reasoning
```

- [ ] **Step 2: Run and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_job_queue_background.py
```

Expected: `2 failed`, each with `AssertionError: Expected run_full_analysis to have been awaited once. Awaited 0 times.` The autospec `TypeError` is raised inside the task and swallowed by its `except`.

- [ ] **Step 3: Implement.** In `/Users/admin/dev2/UpApply/api/app/api/v1/job_queue.py`, replace the call at lines 381-389 (in `_generate_draft_background`):

```python
            ar = await run_full_analysis(
                title=item.title,
                description=item.description or "",
                skills=item.skills or [],
                budget=item.budget_amount,
                client_info=item.client_info,
                profile=profile,
                db=db,
            )
```

with:

```python
            ar = await run_full_analysis(
                db=db,
                user_id=user_id,
                profile=profile,
                job_description=item.description or "",
                job_skills=item.skills or [],
                job_title=item.title,
                budget_amount=item.budget_amount,
                client_info=item.client_info,
            )
```

Then replace the identical block at lines 665-673 (in `_score_pre_filtered_background`) with the same corrected call shown above. The indentation is the same: 12 spaces inside `try:`.

- [ ] **Step 4: Run and confirm it passes**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_job_queue_background.py
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/api/v1/job_queue.py api/tests/test_job_queue_background.py
git commit -m "$(cat <<'EOF'
fix(job-queue): call run_full_analysis with its real signature

Both background tasks (_generate_draft_background and
_score_pre_filtered_background) passed title/description/skills/budget
and omitted user_id, so every queue draft and score-anyway call raised a
swallowed TypeError and silently reset/never scored the item.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 0.3: `CoverLetter.model_used` records the wrong model

`generate_cover_letter` and `regenerate_cover_letter` use `settings.cover_letter_model`, the Claude model. The generate and regenerate endpoints store `settings.default_model` (an OpenAI model, `gpt-4.1-nano` or `gpt-4o` depending on env). `/improve` (`jobs.py:1153`) is already correct.

**Files:**
- Create: `api/tests/test_cover_letter_model_used.py`
- Modify: `api/app/api/v1/jobs.py:859` (`generate_cover_letter_endpoint`) and `api/app/api/v1/jobs.py:979` (`regenerate_cover_letter_endpoint`)

**Interfaces:**
- Consumes: `POST /api/v1/jobs/cover-letters/generate` (`CoverLetterGenerateRequest`), `POST /api/v1/jobs/cover-letters/{letter_id}/regenerate` (`CoverLetterRegenerateRequest`); `settings.cover_letter_model`.
- Produces: `CoverLetterResponse.model_used == settings.cover_letter_model` for both endpoints.

- [ ] **Step 1: Write the failing test** at `/Users/admin/dev2/UpApply/api/tests/test_cover_letter_model_used.py`

```python
"""Regression: CoverLetter.model_used records the model that actually wrote the letter (phase 0)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services.job_analysis import AnalysisResult


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        match_score=70.0,
        skill_matches=[],
        missing_skills=[],
        strengths=[],
        concerns=[],
        deal_breaker_warnings=[],
        relevant_memories=[],
        recommendation="Good match - consider applying",
    )


JOB_DATA = {
    "upwork_url": "https://www.upwork.com/jobs/~01model0used",
    "title": "Build a FastAPI backend",
    "description": "Need an async FastAPI service with Postgres.",
    "skills_required": ["Python", "FastAPI"],
}


@pytest.mark.asyncio
async def test_generate_and_regenerate_record_cover_letter_model(
    client: AsyncClient, auth_headers_with_profile: dict
):
    assert settings.cover_letter_model != settings.default_model

    with patch("app.api.v1.jobs.generate_embedding", AsyncMock(return_value=[0.1] * 1536)), \
         patch("app.api.v1.jobs.run_full_analysis", AsyncMock(return_value=_analysis())), \
         patch("app.api.v1.jobs.find_relevant_proposals", AsyncMock(return_value=[])), \
         patch("app.api.v1.jobs.generate_cover_letter", AsyncMock(return_value="First draft body.")), \
         patch("app.api.v1.jobs.regenerate_cover_letter", AsyncMock(return_value="Second draft body.")):
        r = await client.post(
            "/api/v1/jobs/cover-letters/generate",
            headers=auth_headers_with_profile,
            json={"job_data": JOB_DATA},
        )
        assert r.status_code == 200, r.text
        assert r.json()["model_used"] == settings.cover_letter_model

        r2 = await client.post(
            f"/api/v1/jobs/cover-letters/{r.json()['id']}/regenerate",
            headers=auth_headers_with_profile,
            json={"feedback": "Shorter, lead with the Postgres work."},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["model_used"] == settings.cover_letter_model
```

- [ ] **Step 2: Run and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_cover_letter_model_used.py
```

Expected: `1 failed` with `AssertionError: assert 'gpt-4o' == 'claude-sonnet-4-6'`. The left side is whatever `DEFAULT_MODEL` resolves to locally.

- [ ] **Step 3: Implement.** In `/Users/admin/dev2/UpApply/api/app/api/v1/jobs.py`, change line 859 (inside `CoverLetter(...)` in `generate_cover_letter_endpoint`) from:

```python
        model_used=settings.default_model,
```

to:

```python
        model_used=settings.cover_letter_model,
```

Make the identical change at line 979 (inside `CoverLetter(...)` in `regenerate_cover_letter_endpoint`). Line 687 (`model=settings.default_model` in `/suggest-milestones`) is an OpenAI call and stays unchanged.

- [ ] **Step 4: Run and confirm it passes**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_cover_letter_model_used.py
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/api/v1/jobs.py api/tests/test_cover_letter_model_used.py
git commit -m "$(cat <<'EOF'
fix(cover-letters): record cover_letter_model in model_used

generate and regenerate stored settings.default_model (an OpenAI model)
even though the letter is written by settings.cover_letter_model, which
made model_used useless for comparing pipelines.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 0.4: Declined letters are used and labelled as voice examples

`format_past_proposals` (`api/app/services/cover_letter.py:195-228`) labels `was_hired is False` as `"[SUBMITTED — outcome unknown]"`. The prompt header (`:270-274`) then says "Learn from both". `was_hired=False` is set for DECLINED/WITHDRAWN applications (`applications.py:397`) and for ChatGPT-imported AI letters (`import_chatgpt.py:238`). Neither is Chris's winning voice. `find_relevant_proposals` (`api/app/services/job_analysis.py:776-787`) also lets these rows take up the 3 example slots. The fix excludes them at the SQL level, so they no longer use up slots. `format_past_proposals` also skips them, so no caller can relabel them. `None` (in progress) is labelled `outcome pending`.

**Files:**
- Create: `api/tests/test_past_proposals_voice.py`
- Modify: `api/app/services/cover_letter.py:200-208` (loop head in `format_past_proposals`) and `:272` (prompt header line in `build_user_prompt`)
- Modify: `api/app/services/job_analysis.py:780` (WHERE clause in `find_relevant_proposals`)

**Interfaces:**
- Consumes: `format_past_proposals(proposals: List[Dict]) -> str`, `build_user_prompt(...) -> str`, `find_relevant_proposals(db, user_id, job_description, job_skills, limit=3, successful_only=False) -> List[Dict]`. All signatures are unchanged.
- Produces: `find_relevant_proposals` never returns `was_hired = false` rows; `format_past_proposals` emits only `[WON — This letter got hired ✓]` and `[SUBMITTED — outcome pending]` tiers.

- [ ] **Step 1: Write the failing test** at `/Users/admin/dev2/UpApply/api/tests/test_past_proposals_voice.py`

```python
"""Regression: declined letters are never used or labelled as voice examples (phase 0)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.models.proposal import Proposal
from app.services.cover_letter import build_user_prompt, format_past_proposals
from app.services.job_analysis import find_relevant_proposals
from tests.conftest import TestSessionLocal


def test_format_past_proposals_excludes_declined_letters():
    text = format_past_proposals([
        {"was_hired": True, "job_title": "Won job", "cover_letter_text": "WON LETTER"},
        {"was_hired": False, "job_title": "Lost job", "cover_letter_text": "LOST LETTER"},
        {"was_hired": None, "job_title": "Pending job", "cover_letter_text": "PENDING LETTER"},
    ])
    assert "LOST LETTER" not in text
    assert "outcome unknown" not in text
    assert "Example 1 [WON — This letter got hired ✓] - For: Won job" in text
    assert "Example 2 [SUBMITTED — outcome pending] - For: Pending job" in text


def test_format_past_proposals_all_declined_returns_empty():
    assert format_past_proposals([
        {"was_hired": False, "cover_letter_text": "LOST LETTER"},
    ]) == ""


def test_build_user_prompt_omits_section_when_only_declined_letters():
    profile = MagicMock()
    profile.skills_to_highlight = None
    prompt = build_user_prompt(
        job_title="T",
        job_description="D",
        job_skills=[],
        budget=None,
        skill_matches=[],
        missing_skills=[],
        relevant_memories=[],
        profile=profile,
        past_proposals=[{"was_hired": False, "cover_letter_text": "LOST LETTER"}],
    )
    assert "PAST PROPOSALS" not in prompt
    assert "Learn from both" not in prompt


@pytest.mark.asyncio
async def test_find_relevant_proposals_skips_declined(
    client: AsyncClient, auth_headers: dict
):
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = me.json()["id"]
    vec = [0.1] * 1536
    async with TestSessionLocal() as session:
        session.add_all([
            Proposal(user_id=user_id, cover_letter_text="HIRED", was_hired=True, embedding=vec),
            Proposal(user_id=user_id, cover_letter_text="DECLINED", was_hired=False, embedding=vec),
            Proposal(user_id=user_id, cover_letter_text="PENDING", was_hired=None, embedding=vec),
        ])
        await session.commit()

    async with TestSessionLocal() as session:
        with patch("app.services.job_analysis.generate_embedding", AsyncMock(return_value=vec)):
            proposals = await find_relevant_proposals(
                db=session,
                user_id=user_id,
                job_description="anything",
                job_skills=[],
                limit=3,
            )

    texts = [p["cover_letter_text"] for p in proposals]
    assert texts == ["HIRED", "PENDING"]
```

- [ ] **Step 2: Run and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_past_proposals_voice.py
```

Expected: `4 failed`:
- `'LOST LETTER' not in ...`
- `assert 'Example 1 [SUBMITTED — outcome unknown]\nLOST LETTER' == ''`
- `'PAST PROPOSALS' not in ...`
- `assert ['HIRED', 'DECLINED', 'PENDING'] == ['HIRED', 'PENDING']`

- [ ] **Step 3: Implement (format).** In `/Users/admin/dev2/UpApply/api/app/services/cover_letter.py`, replace lines 200-208:

```python
    formatted = []
    for i, prop in enumerate(proposals, 1):
        was_hired = prop.get("was_hired")
        if was_hired is True:
            tier = "[WON — This letter got hired ✓]"
        elif was_hired is False:
            tier = "[SUBMITTED — outcome unknown]"
        else:
            tier = "[PAST PROPOSAL]"
        entry = f"Example {i} {tier}"
```

with:

```python
    # Declined/lost letters (was_hired is False) are never voice examples.
    voice_proposals = [p for p in proposals if p.get("was_hired") is not False]

    formatted = []
    for i, prop in enumerate(voice_proposals, 1):
        if prop.get("was_hired") is True:
            tier = "[WON — This letter got hired ✓]"
        else:
            tier = "[SUBMITTED — outcome pending]"
        entry = f"Example {i} {tier}"
```

Then replace line 272:

```python
                f"WON letters are ground truth. SUBMITTED letters show voice. Learn from both:\n"
```

with:

```python
                f"WON letters are ground truth. SUBMITTED letters show voice only:\n"
```

(The existing `if past_proposals_text:` guard at line 269 drops the whole section when only declined letters were passed.)

- [ ] **Step 4: Implement (SQL).** In `/Users/admin/dev2/UpApply/api/app/services/job_analysis.py`, inside `find_relevant_proposals`, replace lines 779-781:

```python
        WHERE user_id = :user_id
        AND embedding IS NOT NULL
        """ + ("AND was_hired = true" if successful_only else "") + """
```

with:

```python
        WHERE user_id = :user_id
        AND embedding IS NOT NULL
        AND was_hired IS DISTINCT FROM false
        """ + ("AND was_hired = true" if successful_only else "") + """
```

- [ ] **Step 5: Run and confirm it passes**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_past_proposals_voice.py tests/test_cover_letter.py
```

Expected: all passed, with `4 passed` from the new file and no regressions in `test_cover_letter.py`.

- [ ] **Step 6: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/services/cover_letter.py api/app/services/job_analysis.py api/tests/test_past_proposals_voice.py
git commit -m "$(cat <<'EOF'
fix(cover-letters): stop using declined letters as voice examples

was_hired=false proposals (declined/withdrawn applications and
ChatGPT-imported AI letters) were retrieved into the 3 voice slots and
labelled "outcome unknown - learn from both". Exclude them in
find_relevant_proposals and skip them in format_past_proposals; label
in-progress letters "outcome pending".

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 0.5: `winning_proposal_to_memory` builds a `Memory` with nonexistent fields

`api/agent/learning_engine.py:83-91` passes `memory_type=`, `importance=` and `metadata=`, none of which exist on `Memory` (`api/app/models/memory.py`). It also omits the required `title`. The resulting `TypeError` is swallowed by the caller (`api/app/api/v1/job_queue.py:769-779`), so invited/hired letters never reach memory. The function is still called and is not superseded until later phases, so this task makes it build a valid row with the real columns (`title`, `category`, `source`, `importance_score`).

**Files:**
- Create: `api/tests/test_learning_engine.py`
- Modify: `api/agent/learning_engine.py:83-91`

**Interfaces:**
- Consumes: `Memory(id, user_id, title, content, category, source, importance_score, embedding)`; `generate_embedding` (patched as `agent.learning_engine.generate_embedding`).
- Produces: `winning_proposal_to_memory(user_id: str, job_title: str, job_description: str, cover_letter_text: str, db: AsyncSession) -> None` (signature unchanged) now adds a `Memory` with `title="Won: <job_title>"[:500]`, `category="achievement"`, `source="job_won"`, `importance_score=0.95`.

- [ ] **Step 1: Write the failing test** at `/Users/admin/dev2/UpApply/api/tests/test_learning_engine.py`

```python
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
```

- [ ] **Step 2: Run and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_learning_engine.py
```

Expected: `2 failed`, each with `TypeError: 'memory_type' is an invalid keyword argument for Memory`.

- [ ] **Step 3: Implement.** In `/Users/admin/dev2/UpApply/api/agent/learning_engine.py`, replace lines 83-91:

```python
    memory = Memory(
        id=str(uuid4()),
        user_id=user_id,
        content=combined,
        memory_type="proposal",
        importance=0.95,
        embedding=embedding,
        metadata={"source": "agent_won", "job_title": job_title},
    )
```

with:

```python
    memory = Memory(
        id=str(uuid4()),
        user_id=user_id,
        title=f"Won: {job_title}"[:500],
        content=combined,
        category="achievement",
        source="job_won",
        importance_score=0.95,
        embedding=embedding,
    )
```

- [ ] **Step 4: Run and confirm it passes**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_learning_engine.py
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/agent/learning_engine.py api/tests/test_learning_engine.py
git commit -m "$(cat <<'EOF'
fix(learning): build a valid Memory in winning_proposal_to_memory

The constructor passed memory_type/importance/metadata (not Memory
columns) and omitted the required title, so every invited/hired letter
raised a swallowed TypeError and never reached the memory corpus.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 0.6: Redact the plaintext password and partial API key

There are three locations:
- `scripts/import_upwork_html.py:8` is **untracked** and holds the plaintext UpApply login password in its usage docstring.
- `docs/SESSION_CONTEXT_2026-06-18.md:19,25` is **untracked** and holds a partial OpenAI key prefix (`sk-proj-` plus four characters).
- `docs/SESSION_CONTEXT_2026-03-11.md:122` was found during planning: the **same plaintext password**, in a **tracked** file, committed in `3b7affc` and pushed to `origin` (GitHub).

The two untracked files are edited in place and **not** `git add`ed; this phase does not decide whether to track them. The tracked file is redacted and committed. Its history still contains the password, so rotating it is a human handoff (below). The commands below match the secret with a pattern and never spell it out, so the password never appears in the plan, shell history or commit diff text beyond the existing history.

**Files:**
- Modify (untracked, not staged): `scripts/import_upwork_html.py:8`
- Modify (untracked, not staged): `docs/SESSION_CONTEXT_2026-06-18.md:19,25`
- Modify (tracked, committed): `docs/SESSION_CONTEXT_2026-03-11.md:122`

**Interfaces:**
- Consumes: none
- Produces: none (no code paths change)

- [ ] **Step 1: Write the failing check.** This task changes no code, so the check is a grep that must return no matches afterwards:

```bash
cd /Users/admin/dev2/UpApply
grep -nE -- "--password '[^<]|'--password', '[^<]|sk-proj-[A-Za-z0-9_-]+\.\.\." \
  scripts/import_upwork_html.py docs/SESSION_CONTEXT_2026-03-11.md docs/SESSION_CONTEXT_2026-06-18.md
```

- [ ] **Step 2: Run and confirm it "fails"** (it finds secrets). Expected: 4 matching lines:
  - `scripts/import_upwork_html.py:8`
  - `docs/SESSION_CONTEXT_2026-03-11.md:122`
  - `docs/SESSION_CONTEXT_2026-06-18.md:19`
  - `docs/SESSION_CONTEXT_2026-06-18.md:25`

- [ ] **Step 3: Redact**

```bash
cd /Users/admin/dev2/UpApply
perl -i -pe 's/(--password \x27)[^\x27]*\x27/${1}<password>\x27/' scripts/import_upwork_html.py
perl -i -pe 's/(\x27--password\x27, \x27)[^\x27]*\x27/${1}<password>\x27/' docs/SESSION_CONTEXT_2026-03-11.md
perl -i -pe 's/sk-proj-[A-Za-z0-9_-]+\.\.\./sk-proj-[REDACTED]/g' docs/SESSION_CONTEXT_2026-06-18.md
```

After the redaction:
- `scripts/import_upwork_html.py` line 8 reads `        --password '<password>' \`
- `docs/SESSION_CONTEXT_2026-03-11.md` line 122 reads `  '--email', 'chris@servicevision.net', '--password', '<password>',`
- `docs/SESSION_CONTEXT_2026-06-18.md` lines 19/25 read `` `sk-proj-[REDACTED]` ``

- [ ] **Step 4: Run the check again and confirm it passes**

```bash
cd /Users/admin/dev2/UpApply
grep -nE -- "--password '[^<]|'--password', '[^<]|sk-proj-[A-Za-z0-9_-]+\.\.\." \
  scripts/import_upwork_html.py docs/SESSION_CONTEXT_2026-03-11.md docs/SESSION_CONTEXT_2026-06-18.md; echo "exit=$?"
grep -n -- "--password" scripts/import_upwork_html.py docs/SESSION_CONTEXT_2026-03-11.md
grep -n "sk-proj-" docs/SESSION_CONTEXT_2026-06-18.md
git status --short scripts/import_upwork_html.py docs/SESSION_CONTEXT_2026-06-18.md docs/SESSION_CONTEXT_2026-03-11.md
```

Expected:
- The first grep prints nothing and `exit=1`.
- The second shows only `<password>` values, plus the argparse line `parser.add_argument("--password", required=True)` at `import_upwork_html.py:152`.
- The third shows only `sk-proj-[REDACTED]`.
- `git status` shows `?? scripts/import_upwork_html.py`, `?? docs/SESSION_CONTEXT_2026-06-18.md` (still untracked) and ` M docs/SESSION_CONTEXT_2026-03-11.md`.

- [ ] **Step 5: Commit (tracked file only; the two untracked files are intentionally NOT added)**

```bash
cd /Users/admin/dev2/UpApply
git add docs/SESSION_CONTEXT_2026-03-11.md
git commit -m "$(cat <<'EOF'
chore(security): redact plaintext password from 2026-03-11 session doc

The value remains in git history (3b7affc) and must be rotated.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Phase 0 exit criteria

```bash
# Full API suite: baseline 191 + 11 new = 202 passing, 0 failures
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q
# Import smoke test from CLAUDE.md
cd /Users/admin/dev2/UpApply/api && ./venv/bin/python -c "from app.main import app; print('OK')"
# Extension untouched but must still type-check
cd /Users/admin/dev2/UpApply/extension && npm run type-check
# No secrets left in the working tree files touched by Task 0.6 (must print nothing)
cd /Users/admin/dev2/UpApply && grep -nE -- "--password '[^<]|'--password', '[^<]|sk-proj-[A-Za-z0-9_-]+\.\.\." scripts/import_upwork_html.py docs/SESSION_CONTEXT_2026-03-11.md docs/SESSION_CONTEXT_2026-06-18.md
# Branch contains exactly the 6 phase-0 commits and no extension/ or working/ paths
cd /Users/admin/dev2/UpApply && git log --oneline main..feat/mdg-0-bleeding && git diff --stat main..feat/mdg-0-bleeding
```

The exit criteria were verified while writing this plan: all five code fixes applied together give `202 passed`.

---

## Phase 1: Knowledge Layer

This phase builds the two separate stores from spec §1. The first is `facts`, a new table of atomic claims with pgvector embeddings and a review status. The second is voice samples, which reuse the existing `proposals` table with new columns `author`, `outcome`, `job_text`, `screening_answers` and `job_needs_embedding`. Migration 022 adds `memories.exclude_from_retrieval`. Its data step flags the roughly 800 ChatGPT-corpus `JOB POSTING:` memories so retrieval skips them, and it re-tags ChatGPT-imported proposals as `author='ai'`. On top of the schema come these pieces: a thin Anthropic `structured_call` seam, a Haiku fact extractor, and a facts service that handles embedding, dedupe at 0.92, auto-approve, merge, search and crediting. A `/api/v1/facts` router provides review, manual facts, ingest, bio-memories → facts and proposals → facts. The phase also adds a ChatGPT-export ingestion script and extends `/proposals/import-from-upwork` to carry full letters, screening answers, job text and outcome. On the extension side, the proposal-detail scraper now captures answers and the job description separately, and a new **Facts** review tab appears under **Me**. Generation does not read facts yet; that is Phase 2. The only change in generation behaviour is that excluded corpus memories stop surfacing in `job_analysis.py` retrieval.

**Branch:** `feat/mdg-1-knowledge`, stacked on `feat/mdg-0-bleeding`.

```bash
cd /Users/admin/dev2/UpApply
git checkout feat/mdg-0-bleeding
git checkout -b feat/mdg-1-knowledge
```

**Conventions used throughout this phase**
- IDs follow the repo's existing pattern of `String(36)` UUID strings, not the native `UUID` type, because `users.id` is `String(36)` and every FK in the repo is a string. Wherever the shared contract says `UUID`, read it as a `str` UUID.
- Unit tests never call OpenAI or Anthropic. They patch `generate_embedding` in the importing module and patch `structured_call` or `extract_facts`.
- API test command (shown once, used in every task):
  `cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q <target>`

---

### Task 1.1: Migration 022, Fact model, voice-sample and memory columns, test fixtures

**Files:**
- Create: `api/alembic/versions/022_knowledge_layer.py`
- Create: `api/app/models/fact.py`
- Modify: `api/app/models/__init__.py` (lines 18 and 39: import and export `Fact`)
- Modify: `api/app/models/proposal.py` (line 6 imports; insert columns after the `source` column, lines 72-75; `__table_args__` lines 92-99)
- Modify: `api/app/models/memory.py` (line 6 imports; insert the column after `importance_score`, line 60)
- Modify: `api/tests/conftest.py` (line 81 TRUNCATE list; append the `db_session` and `test_user` fixtures)
- Create: `api/tests/vector_utils.py`
- Create: `api/tests/test_fact_model.py`

**Interfaces:**
- Produces: `app.models.fact.Fact` (table `facts`, with `FACT_KINDS`, `FACT_STATUSES` and `JOB_TYPES` tuples); `Proposal.author|outcome|job_text|screening_answers|job_needs_embedding|facts_ingested_at`; `Memory.exclude_from_retrieval`; alembic revision `022_knowledge_layer`.
- Produces (test helpers): fixtures `db_session` and `test_user`; `tests.vector_utils.unit(i)`, `blend(i, j, cos)` and `make_fake_embedder()`.
- Contract additions: `proposals.screening_answers JSONB` holds voice-sample answers (the contract lists no column for them, but spec §1.3 requires capturing them). `proposals.facts_ingested_at TIMESTAMPTZ` marks letters already run through fact extraction, so `/facts/from-proposals` never re-extracts a letter that yielded zero facts (Task 1.6).

- [ ] **Step 1: Write the test helpers and the failing model test**

`api/tests/vector_utils.py`:
```python
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
```

Append to `api/tests/conftest.py`:
```python
@pytest_asyncio.fixture(loop_scope="session")
async def db_session(setup_database):
    """Plain AsyncSession for service-level DB tests; tables are truncated afterwards."""
    async with TestSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE TABLE facts, proposals, memories, user_profiles, users "
            "RESTART IDENTITY CASCADE"
        ))


@pytest_asyncio.fixture(loop_scope="session")
async def test_user(db_session):
    """A committed User row for service-level tests."""
    from app.models.user import User

    user = User(email="facts-owner@example.com", hashed_password="not-a-real-hash")
    db_session.add(user)
    await db_session.commit()
    return user
```

`api/tests/test_fact_model.py`:
```python
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
```

- [ ] **Step 2: Run the test and confirm it fails**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_fact_model.py`
Expected: FAIL, collection error `ModuleNotFoundError: No module named 'app.models.fact'`.

- [ ] **Step 3: Implement the model, columns, conftest TRUNCATE and migration**

`api/app/models/fact.py`:
```python
"""Fact model — atomic, verified claims about the user that generation may cite."""
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.database import Base
from app.core.config import settings

FACT_KINDS = ("project", "metric", "credential", "client_quote", "role", "tech", "outcome")
FACT_STATUSES = ("candidate", "approved", "rejected")
JOB_TYPES = ("cto", "saas", "sql", "cloud", "ai", "fullstack")


class Fact(Base):
    """One atomic claim (what to say). Only status='approved' rows are retrievable.

    ARRAY/JSONB columns are not mutation-tracked: always assign a new list.
    """

    __tablename__ = "facts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    skills: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    industries: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    job_types: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )

    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default="0.5")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="candidate", server_default="candidate"
    )

    # First source that produced the fact; `sources` holds every merged provenance entry
    # as {"source_type", "source_ref", "snippet"}.
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    times_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    times_in_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Embeds statement + detail only
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_facts_user_status", "user_id", "status"),
        Index(
            "ix_facts_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
```

`api/app/models/__init__.py`: after line 18 add `from app.models.fact import Fact`, and append `"Fact",` to `__all__` after `"GlobalSignalPool",`.

`api/app/models/proposal.py`, line 6:
```python
from sqlalchemy import DateTime, String, Text, Numeric, Boolean, func, ForeignKey, Index
```
stays unchanged. Insert after the `source` column (after line 75, before `# Timestamps`):
```python
    # Voice-sample metadata (migration 022). Only author != 'ai' rows are voice examples.
    author: Mapped[str] = mapped_column(
        String(20), nullable=False, default="chris", server_default="chris"
    )  # chris, chris_edited_ai, ai
    outcome: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # no_response, viewed, replied, interviewed, hired, declined
    job_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screening_answers: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True
    )  # [{"question": str, "answer": str}]
    # Embedding of the JOB (title + description) so voice retrieval is job<->job
    job_needs_embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=True
    )
    # Set once /facts/from-proposals (or PUT /final) has run extraction on this letter,
    # including runs that yielded zero facts, so the queue always advances.
    facts_ingested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```
Replace `__table_args__` (lines 92-99) with:
```python
    __table_args__ = (
        Index(
            "ix_proposals_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_proposals_job_needs_embedding_hnsw",
            "job_needs_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"job_needs_embedding": "vector_cosine_ops"},
        ),
    )
```

`api/app/models/memory.py`, line 6 becomes:
```python
from sqlalchemy import Boolean, DateTime, String, Text, Numeric, false, func, ForeignKey, Index
```
After line 60 (`importance_score`), insert:
```python
    # Corpus "JOB POSTING:" rows are ingestion input only — never retrieved (migration 022)
    exclude_from_retrieval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
```

`api/tests/conftest.py` line 81: change `"job_reviews, work_logs, "` to `"job_reviews, work_logs, facts, "`.

`api/alembic/versions/022_knowledge_layer.py`:
```python
"""Knowledge layer: facts table, voice-sample columns on proposals, memory retrieval flag.

Revision ID: 022_knowledge_layer
Revises: 021_global_signal_pool
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from pgvector.sqlalchemy import Vector

revision = '022_knowledge_layer'
down_revision = '021_global_signal_pool'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'facts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('statement', sa.Text(), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('skills', ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('industries', ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('job_types', ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('strength', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('status', sa.String(20), nullable=False, server_default='candidate'),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_ref', sa.String(200), nullable=True),
        sa.Column('sources', JSONB(), nullable=False, server_default='[]'),
        sa.Column('times_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('times_in_won', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_facts_user_id', 'facts', ['user_id'])
    op.create_index('ix_facts_user_status', 'facts', ['user_id', 'status'])
    op.execute(
        "CREATE INDEX ix_facts_embedding_hnsw ON facts "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # Voice samples = proposals + author/outcome/job context
    op.add_column('proposals', sa.Column('author', sa.String(20), nullable=False, server_default='chris'))
    op.add_column('proposals', sa.Column('outcome', sa.String(20), nullable=True))
    op.add_column('proposals', sa.Column('job_text', sa.Text(), nullable=True))
    op.add_column('proposals', sa.Column('screening_answers', JSONB(), nullable=True))
    op.add_column('proposals', sa.Column('job_needs_embedding', Vector(1536), nullable=True))
    op.add_column('proposals', sa.Column('facts_ingested_at', sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "CREATE INDEX ix_proposals_job_needs_embedding_hnsw ON proposals "
        "USING hnsw (job_needs_embedding vector_cosine_ops)"
    )

    op.add_column(
        'memories',
        sa.Column('exclude_from_retrieval', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # --- Data step (flag/re-tag only; nothing is deleted) ---
    # Corpus memories built by scripts/import_chatgpt_corpus.py:build_proposal_memory start
    # with "JOB POSTING:" — they are strangers' job posts, never portfolio evidence.
    op.execute("UPDATE memories SET exclude_from_retrieval = true WHERE content LIKE 'JOB POSTING:%'")
    # Letters created by api/app/api/v1/import_chatgpt.py are ChatGPT-authored.
    op.execute("UPDATE proposals SET author = 'ai' WHERE source = 'chatgpt_import'")
    # Extension-sourced rows started as UpApply drafts (jobs.py submit + applications.py promote).
    op.execute("UPDATE proposals SET author = 'chris_edited_ai' WHERE source = 'extension'")
    # Outcome backfill from legacy flags so voice retrieval can be outcome-weighted.
    op.execute("UPDATE proposals SET outcome = 'hired' WHERE was_hired = true")
    op.execute(
        "UPDATE proposals SET outcome = 'interviewed' "
        "WHERE outcome IS NULL AND status IN ('interviewed', 'interview')"
    )
    op.execute(
        "UPDATE proposals SET outcome = 'replied' "
        "WHERE outcome IS NULL AND (client_responded = true OR status IN ('responded', 'active'))"
    )


def downgrade() -> None:
    op.drop_column('memories', 'exclude_from_retrieval')
    op.execute("DROP INDEX IF EXISTS ix_proposals_job_needs_embedding_hnsw")
    op.drop_column('proposals', 'facts_ingested_at')
    op.drop_column('proposals', 'job_needs_embedding')
    op.drop_column('proposals', 'screening_answers')
    op.drop_column('proposals', 'job_text')
    op.drop_column('proposals', 'outcome')
    op.drop_column('proposals', 'author')
    op.drop_table('facts')
```

- [ ] **Step 4: Run the model tests and confirm they pass**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_fact_model.py`
Expected: `3 passed`.

- [ ] **Step 5: Verify the migration and its data step on a scratch database**

```bash
cd /Users/admin/dev2/UpApply/api
export PGPASSWORD=upapply
psql -h localhost -p 55499 -U upapply -d postgres -c "DROP DATABASE IF EXISTS upapply_migr" -c "CREATE DATABASE upapply_migr"
psql -h localhost -p 55499 -U upapply -d upapply_migr -c "CREATE EXTENSION IF NOT EXISTS vector"
export DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_migr
./venv/bin/alembic upgrade 021_global_signal_pool
psql -h localhost -p 55499 -U upapply -d upapply_migr <<'SQL'
INSERT INTO users (id, email, hashed_password, is_active, is_verified) VALUES ('u1', 'm@example.com', 'x', true, false);
INSERT INTO memories (id, user_id, title, content, importance_score) VALUES
  ('m1', 'u1', 'Past Proposal: X', E'JOB POSTING:\nNeed a dev\n\nPROPOSAL WRITTEN:\n...', 0.8),
  ('m2', 'u1', 'Stratavault.ai', 'Built Stratavault.ai', 1.0);
INSERT INTO proposals (id, user_id, cover_letter_text, source, was_hired, status) VALUES
  ('p1', 'u1', 'ChatGPT letter', 'chatgpt_import', false, 'imported'),
  ('p2', 'u1', 'Scraped letter', 'scraped', true, 'hired'),
  ('p3', 'u1', 'Extension letter', 'extension', null, 'interviewed');
SQL
./venv/bin/alembic upgrade head
psql -h localhost -p 55499 -U upapply -d upapply_migr -At \
  -c "SELECT id, exclude_from_retrieval FROM memories ORDER BY id" \
  -c "SELECT id, author, coalesce(outcome,'-') FROM proposals ORDER BY id" \
  -c "SELECT indexname FROM pg_indexes WHERE tablename IN ('facts','proposals') AND indexname LIKE '%hnsw%' ORDER BY 1"
./venv/bin/alembic downgrade 021_global_signal_pool && ./venv/bin/alembic upgrade head
psql -h localhost -p 55499 -U upapply -d postgres -c "DROP DATABASE upapply_migr"
unset DATABASE_URL PGPASSWORD
```
Expected output from the checks:
```
m1|t
m2|f
p1|ai|-
p2|chris|hired
p3|chris_edited_ai|interviewed
ix_facts_embedding_hnsw
ix_proposals_embedding_hnsw
ix_proposals_job_needs_embedding_hnsw
```
The downgrade then re-upgrade must finish without errors.

- [ ] **Step 6: Run the full suite (no regressions)**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q`
Expected: all pass (the Phase 0 baseline plus 3).

- [ ] **Step 7: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/alembic/versions/022_knowledge_layer.py api/app/models/fact.py api/app/models/__init__.py \
  api/app/models/proposal.py api/app/models/memory.py api/tests/conftest.py \
  api/tests/vector_utils.py api/tests/test_fact_model.py
git commit -m "$(cat <<'EOF'
feat(knowledge): migration 022 — facts table, voice-sample columns, memory exclusion flag

Adds the facts table (pgvector HNSW), author/outcome/job_text/screening_answers/
job_needs_embedding/facts_ingested_at on proposals, and memories.exclude_from_retrieval. Data step
flags JOB POSTING corpus memories and re-tags chatgpt_import proposals author='ai'.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.2: `services/llm.py`, a structured-output seam, plus the `extraction_model` setting

**Files:**
- Create: `api/app/services/llm.py`
- Modify: `api/app/core/config.py` (insert after line 70 `cover_letter_model`)
- Create: `api/tests/test_llm.py`

**Interfaces:**
- Produces: `get_anthropic_client() -> AsyncAnthropic`; `async structured_call(model: str, system: str | list, user: str, schema: dict, effort: str | None = None, max_tokens: int = 16000) -> dict`; `class LLMError(RuntimeError)`; `settings.extraction_model = "claude-haiku-4-5"`. Every failure (API error, refusal, truncation, missing text, invalid JSON) surfaces as `LLMError`, so endpoints can map it to a 502.
- Phase 2 consumes this module. It changes `cover_letter_model` to `claude-opus-5-5` and adds `writer_effort`; this phase adds only `extraction_model`.

- [ ] **Step 1: Write the failing test**

`api/tests/test_llm.py`:
```python
"""Tests for the structured-output LLM seam (Anthropic client fully mocked)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services import llm
from app.services.llm import LLMError, structured_call

SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "integer"}},
    "required": ["a"],
    "additionalProperties": False,
}


def _fake_client(text: str = '{"a": 1}', stop_reason: str = "end_turn") -> MagicMock:
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    ))
    return client


@pytest.mark.asyncio
async def test_structured_call_sends_json_schema_and_effort():
    client = _fake_client()
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        result = await structured_call("claude-opus-5-5", "sys", "hello", SCHEMA, effort="high")

    assert result == {"a": 1}
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "hello"}]
    assert kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": SCHEMA},
        "effort": "high",
    }
    # Opus 5.5 rejects these — they must never be sent
    assert "temperature" not in kwargs
    assert "thinking" not in kwargs
    assert "tool_choice" not in kwargs


@pytest.mark.asyncio
async def test_structured_call_omits_effort_when_none():
    client = _fake_client()
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)
    assert "effort" not in client.messages.create.call_args.kwargs["output_config"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
async def test_structured_call_raises_on_bad_stop(stop_reason):
    with patch("app.services.llm.get_anthropic_client", return_value=_fake_client(stop_reason=stop_reason)):
        with pytest.raises(LLMError):
            await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)


@pytest.mark.asyncio
async def test_structured_call_raises_on_invalid_json():
    with patch("app.services.llm.get_anthropic_client", return_value=_fake_client(text="not json")):
        with pytest.raises(LLMError):
            await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)


@pytest.mark.asyncio
async def test_structured_call_prose_reply_names_the_proxy():
    """A proxy that strips output_config yields prose, not JSON."""
    prose = 'Sure! Here is the JSON you asked for:\n```json\n{"a": 1}\n```'
    with patch("app.services.llm.get_anthropic_client", return_value=_fake_client(text=prose)):
        with pytest.raises(LLMError, match="output_config"):
            await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)


@pytest.mark.asyncio
async def test_structured_call_wraps_api_errors():
    """A proxy that rejects output_config returns HTTP 400; callers only ever see LLMError."""
    import httpx
    from anthropic import BadRequestError

    request = httpx.Request("POST", "https://proxy.example.com/v1/messages")
    error = BadRequestError(
        "output_config: Extra inputs are not permitted",
        response=httpx.Response(400, request=request),
        body=None,
    )
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=error)
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        with pytest.raises(LLMError, match="output_config"):
            await structured_call("claude-haiku-4-5", "sys", "hello", SCHEMA)


def test_get_anthropic_client_uses_base_url(monkeypatch):
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(settings, "anthropic_base_url", "https://proxy.example.com/")
    client = llm.get_anthropic_client()
    assert str(client.base_url) == "https://proxy.example.com/"
    assert llm.get_anthropic_client() is client
    monkeypatch.setattr(llm, "_client", None)


def test_extraction_model_default():
    assert settings.extraction_model == "claude-haiku-4-5"
```

- [ ] **Step 2: Run the test and confirm it fails**

`cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_llm.py`
Expected: FAIL with `ImportError: cannot import name 'llm' from 'app.services'`.

- [ ] **Step 3: Implement**

In `api/app/core/config.py`, after line 70 (`cover_letter_model: str = "claude-sonnet-4-6"`):
```python
    extraction_model: str = "claude-haiku-4-5"   # fact extraction, job brief, claim check
```

`api/app/services/llm.py`:
```python
"""Anthropic structured-output seam for the memory-driven generation pipeline.

Every new LLM call goes through structured_call so tests mock one function.
Honours Opus 5.5 constraints: no temperature, no thinking param (effort is the
only depth control), no assistant prefill, no forced tool_choice — the response
shape comes from output_config.format (JSON-schema structured outputs).
"""
import json
import logging
from typing import Optional, Union

from anthropic import APIError, AsyncAnthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncAnthropic] = None

# Shown when the reply is not the requested JSON: the usual cause is a proxy
# (ANTHROPIC_BASE_URL) that drops or rejects output_config.
PROXY_HINT = "check that ANTHROPIC_BASE_URL passes output_config through"


class LLMError(RuntimeError):
    """A structured call produced no usable JSON (refusal, truncation, bad JSON)."""


def get_anthropic_client() -> AsyncAnthropic:
    """Process-wide AsyncAnthropic client; honours ANTHROPIC_BASE_URL (AICostCentral proxy)."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url or None,
        )
    return _client


async def structured_call(
    model: str,
    system: Union[str, list],
    user: str,
    schema: dict,
    effort: Optional[str] = None,
    max_tokens: int = 16000,
) -> dict:
    """Single-turn call whose reply is guaranteed to match `schema`; returns the parsed dict."""
    output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config["effort"] = effort

    try:
        response = await get_anthropic_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config=output_config,
        )
    except APIError as exc:
        raise LLMError(f"structured_call API error from {model}: {exc} ({PROXY_HINT})") from exc

    if response.stop_reason in ("refusal", "max_tokens"):
        raise LLMError(f"structured_call stopped with {response.stop_reason} (model={model})")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise LLMError(f"structured_call returned no text block (model={model})")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("structured_call invalid JSON from %s: %.200s", model, text)
        raise LLMError(f"structured_call returned invalid JSON (model={model}; {PROXY_HINT})") from exc
```

- [ ] **Step 4: Run the test and confirm it passes**

`cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_llm.py`
Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/services/llm.py api/app/core/config.py api/tests/test_llm.py
git commit -m "$(cat <<'EOF'
feat(llm): structured_call seam (output_config json_schema) + extraction_model setting

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.3: Fact schemas and the Haiku fact extractor

**Files:**
- Create: `api/app/schemas/fact.py`
- Create: `api/app/services/fact_extraction.py`
- Create: `api/tests/test_fact_extraction.py`

**Interfaces:**
- Consumes: `structured_call` and `settings.extraction_model` from Task 1.2.
- Produces: `FactCandidate`, `FactCreate`, `FactUpdate`, `FactOut`, `FactIngestItem`, `FactIngestRequest`, `FactIngestResult` and `FactBulkApprove`; `async extract_facts(text: str, source_type: str, source_ref: str | None = None, context: str | None = None) -> list[FactCandidate]`.
- Contract additions: `FactCandidate.source_snippet: str | None = None` stores the verbatim evidence quote shown in Facts review. `FactIngestResult` adds `skipped`, `failed` and `remaining` beyond `{created, merged, auto_approved}`.

- [ ] **Step 1: Write the failing test**

`api/tests/test_fact_extraction.py`:
```python
"""Tests for LLM fact extraction (structured_call mocked)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.schemas.fact import FactCandidate
from app.services.fact_extraction import FACT_EXTRACTION_SCHEMA, extract_facts

RAW = {
    "facts": [
        {
            "kind": "metric",
            "statement": "Migrated a 160-server datacenter to Azure hybrid cloud.",
            "detail": "",
            "skills": ["Azure", "SQL Server"],
            "industries": ["Education"],
            "job_types": ["cloud", "sql", "bogus"],
            "strength": 1.4,
            "evidence_quote": "it was 160 servers, not 120",
        },
        {
            "kind": "not-a-kind",
            "statement": "Should be dropped.",
            "detail": "",
            "skills": [],
            "industries": [],
            "job_types": [],
            "strength": 0.5,
            "evidence_quote": "",
        },
        {
            "kind": "project",
            "statement": "   ",
            "detail": "",
            "skills": [],
            "industries": [],
            "job_types": [],
            "strength": 0.5,
            "evidence_quote": "",
        },
    ]
}


@pytest.mark.asyncio
async def test_extract_facts_maps_and_cleans_candidates():
    mock = AsyncMock(return_value=RAW)
    with patch("app.services.fact_extraction.structured_call", mock):
        cands = await extract_facts(
            "Correction: it was 160 servers, not 120.",
            source_type="chatgpt_user_turn",
            source_ref="conv-1",
            context="Final letter: ...migrated 120 servers...",
        )

    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c, FactCandidate)
    assert c.kind == "metric"
    assert c.detail is None
    assert c.job_types == ["cloud", "sql"]
    assert c.strength == 1.0
    assert c.source_type == "chatgpt_user_turn"
    assert c.source_ref == "conv-1"
    assert c.source_snippet == "it was 160 servers, not 120"

    kwargs = mock.call_args.kwargs
    assert kwargs["model"] == settings.extraction_model
    assert kwargs["schema"] is FACT_EXTRACTION_SCHEMA
    assert "effort" not in kwargs  # Haiku 4.5 rejects effort
    assert "SOURCE TEXT" in kwargs["user"]
    assert "CONTEXT" in kwargs["user"]
    assert "Final letter" in kwargs["user"]


@pytest.mark.asyncio
async def test_extract_facts_without_context_has_no_context_block():
    mock = AsyncMock(return_value={"facts": []})
    with patch("app.services.fact_extraction.structured_call", mock):
        assert await extract_facts("Built Stratavault.ai", source_type="bio_memory") == []
    assert "CONTEXT" not in mock.call_args.kwargs["user"]


@pytest.mark.asyncio
async def test_extract_facts_skips_blank_text():
    mock = AsyncMock()
    with patch("app.services.fact_extraction.structured_call", mock):
        assert await extract_facts("   ", source_type="bio_memory") == []
    mock.assert_not_called()


def test_schema_is_strict():
    item = FACT_EXTRACTION_SCHEMA["properties"]["facts"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"].keys())
```

- [ ] **Step 2: Run the test and confirm it fails**

`cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_fact_extraction.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.fact'`.

- [ ] **Step 3: Implement**

`api/app/schemas/fact.py`:
```python
"""Fact (knowledge layer) schemas."""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

FactKind = Literal["project", "metric", "credential", "client_quote", "role", "tech", "outcome"]
FactStatus = Literal["candidate", "approved", "rejected"]
JobType = Literal["cto", "saas", "sql", "cloud", "ai", "fullstack"]


class FactCandidate(BaseModel):
    """An extracted (or manually entered) claim, before dedupe/merge."""

    kind: FactKind
    statement: str
    detail: Optional[str] = None
    skills: List[str] = []
    industries: List[str] = []
    job_types: List[JobType] = []
    strength: float = Field(0.5, ge=0.0, le=1.0)
    source_type: str
    source_ref: Optional[str] = None
    source_snippet: Optional[str] = None  # verbatim evidence shown in the Facts review page


class FactCreate(BaseModel):
    """Manual fact entered by the user — stored approved."""

    kind: FactKind
    statement: str
    detail: Optional[str] = None
    skills: List[str] = []
    industries: List[str] = []
    job_types: List[JobType] = []
    strength: float = Field(0.7, ge=0.0, le=1.0)


class FactUpdate(BaseModel):
    statement: Optional[str] = None
    detail: Optional[str] = None
    status: Optional[FactStatus] = None
    kind: Optional[FactKind] = None
    skills: Optional[List[str]] = None
    job_types: Optional[List[JobType]] = None
    strength: Optional[float] = Field(None, ge=0.0, le=1.0)


class FactOut(BaseModel):
    id: str
    kind: str
    statement: str
    detail: Optional[str] = None
    skills: List[str] = []
    industries: List[str] = []
    job_types: List[str] = []
    strength: float
    status: str
    source_type: str
    source_ref: Optional[str] = None
    sources: List[dict] = []
    times_used: int = 0
    times_in_won: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FactIngestItem(BaseModel):
    text: str                       # text written by the user (the only extraction source)
    source_ref: Optional[str] = None
    context: Optional[str] = None   # not-the-user text that helps interpretation; never extracted


class FactIngestRequest(BaseModel):
    source_type: str
    items: List[FactIngestItem] = Field(..., max_length=25)
    auto_approve: bool = False


class FactIngestResult(BaseModel):
    created: int = 0
    merged: int = 0
    auto_approved: int = 0
    skipped: int = 0    # source_ref already ingested
    failed: int = 0     # extraction errors
    remaining: int = 0  # from-proposals: proposals still to process


class FactBulkApprove(BaseModel):
    ids: List[str]
```

`api/app/services/fact_extraction.py`:
```python
"""Extract atomic fact candidates from text the user wrote (cheap model, structured output)."""
import logging
from typing import List, Optional

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.fact import FactCandidate
from app.services.llm import structured_call

logger = logging.getLogger(__name__)

KINDS = ["project", "metric", "credential", "client_quote", "role", "tech", "outcome"]
JOB_TYPES = ["cto", "saas", "sql", "cloud", "ai", "fullstack"]

FACT_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": KINDS},
                    "statement": {"type": "string"},
                    "detail": {"type": "string"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "industries": {"type": "array", "items": {"type": "string"}},
                    "job_types": {"type": "array", "items": {"type": "string", "enum": JOB_TYPES}},
                    "strength": {"type": "number"},
                    "evidence_quote": {"type": "string"},
                },
                "required": [
                    "kind", "statement", "detail", "skills", "industries",
                    "job_types", "strength", "evidence_quote",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}

EXTRACTION_SYSTEM = """\
You build a verified fact bank about one freelancer from text they wrote themselves.
Their proposals will later cite these facts as proof, so every fact must be true to
the SOURCE TEXT and quotable on its own.

What to extract: concrete, checkable claims about the freelancer's own work: projects
they built or led, numbers (servers, users, clients, %, $, years), named clients or
products, credentials and roles, technologies they used in production, outcomes, and
client praise. A correction in the source ("it was 160 servers, not 120") is the most
valuable kind of fact; use the corrected value.

What to skip: the requirements of a client's job post, generic advice, opinions,
writing-style preferences, plans or hypotheticals, and anything about other people's work.

Hard rules:
- Use only the SOURCE TEXT. The CONTEXT block (if present) was not written by the
  freelancer. Use it only to work out what the source refers to. Never extract a claim
  that appears only in CONTEXT.
- Never invent or round numbers, names or dates. Keep them exactly as written.
- One claim per fact. `statement` is 1-2 sentences, starts with a verb or noun phrase
  (no "I"), and reads well when quoted ("Led a 160-server on-prem to Azure migration...").
- `detail`: optional supporting context from the source, or "" if none.
- `kind`: project | metric | credential | client_quote | role | tech | outcome.
- `job_types` (multi-label, may be empty): cto (leadership/advisory/founding),
  saas (SaaS/MVP/product), sql (SQL Server/data), cloud (Azure/AWS/migration/cost),
  ai (LLM/RAG/vector/ML), fullstack (web app build).
- `strength` 0-1: 0.9-1.0 for a hard number plus a named client/product plus an outcome;
  0.6-0.8 for a concrete named project or scoped production work; 0.3-0.5 for a generic
  capability claim.
- `evidence_quote`: a verbatim excerpt of up to 200 characters from the SOURCE TEXT that
  supports the fact.
- If nothing qualifies, return {"facts": []}.
"""


async def extract_facts(
    text: str,
    source_type: str,
    source_ref: Optional[str] = None,
    context: Optional[str] = None,
) -> List[FactCandidate]:
    """Return fact candidates found in `text` (empty list when none)."""
    if not text or not text.strip():
        return []

    user = f"SOURCE TEXT (written by the freelancer):\n<<<\n{text}\n>>>"
    if context:
        user += (
            "\n\nCONTEXT (not written by the freelancer; use it only to interpret the "
            f"source, never extract from it):\n<<<\n{context}\n>>>"
        )

    data = await structured_call(
        model=settings.extraction_model,
        system=EXTRACTION_SYSTEM,
        user=user,
        schema=FACT_EXTRACTION_SCHEMA,
        max_tokens=8000,
    )

    candidates: List[FactCandidate] = []
    for raw in data.get("facts", []):
        statement = (raw.get("statement") or "").strip()
        if not statement:
            continue
        try:
            candidates.append(FactCandidate(
                kind=raw["kind"],
                statement=statement,
                detail=(raw.get("detail") or "").strip() or None,
                skills=[s.strip() for s in raw.get("skills", []) if s and s.strip()],
                industries=[s.strip() for s in raw.get("industries", []) if s and s.strip()],
                job_types=[j for j in raw.get("job_types", []) if j in JOB_TYPES],
                strength=min(1.0, max(0.0, float(raw.get("strength", 0.5)))),
                source_type=source_type,
                source_ref=source_ref,
                source_snippet=(raw.get("evidence_quote") or "").strip()[:300] or None,
            ))
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            logger.warning("Dropping malformed fact candidate (%s): %.120s", exc, statement)
    return candidates
```

- [ ] **Step 4: Run the test and confirm it passes**

`cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_fact_extraction.py`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/schemas/fact.py api/app/services/fact_extraction.py api/tests/test_fact_extraction.py
git commit -m "$(cat <<'EOF'
feat(knowledge): fact schemas + Haiku structured fact extractor

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.4: Facts service with upsert/dedupe/auto-approve, search and credit

**Files:**
- Create: `api/app/services/facts.py`
- Create: `api/tests/test_facts_service.py`

**Interfaces:**
- Consumes: `Fact` (Task 1.1), `FactCandidate` (Task 1.3), `app.core.embeddings.generate_embedding`.
- Produces:
  - `DEDUPE_THRESHOLD = 0.92`
  - `fact_embedding_text(statement: str, detail: str | None) -> str`
  - `async upsert_candidate_outcome(db, user_id, cand: FactCandidate, auto_approve=False) -> tuple[Fact, str]`, where the outcome is one of these values:
    - `created`: a new candidate.
    - `auto_approved`: a new fact created with `auto_approve`, or a merge into an approved fact (§1.7).
    - `merged`: a merge into a candidate or rejected fact.
  - `async upsert_candidate(db, user_id, cand, auto_approve=False) -> Fact`
  - `async search_facts(db, user_id, query_embedding: list[float], limit=8, status='approved') -> list[tuple[Fact, float]]`
  - `async credit_facts(db, fact_ids: list[str], won: bool) -> None`. With `won=False` it increments `times_used` (Phase 2 orchestrator, once per draft). With `won=True` it increments `times_in_won` (Phase 3 outcome sync).
- Behaviour: none of these functions commit; they flush only. Matching considers every status. Approved wording is never overwritten. For unreviewed facts the stronger wording wins, and `strength` takes the max. When `auto_approve` is set, a matched candidate is promoted, but a rejected fact stays rejected.

- [ ] **Step 1: Write the failing test**

`api/tests/test_facts_service.py`:
```python
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
    assert fact.strength == 0.9
    assert fact.skills == ["Azure", "SQL Server"]
    assert [s["source_ref"] for s in fact.sources] == ["m1", "p1"]
    assert await _count(db_session) == 1


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
    await credit_facts(db_session, [fact.id], won=False)
    await credit_facts(db_session, [fact.id], won=False)
    await credit_facts(db_session, [fact.id], won=True)
    await credit_facts(db_session, [], won=True)
    await db_session.refresh(fact)
    assert fact.times_used == 2
    assert fact.times_in_won == 1
```

- [ ] **Step 2: Run the test and confirm it fails**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_facts_service.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.facts'`.

- [ ] **Step 3: Implement**

`api/app/services/facts.py`:
```python
"""Fact store: embedding, dedupe/merge, auto-approve, semantic search, outcome crediting.

Nothing here commits — callers own the transaction (routers commit; get_db commits too).
"""
import logging
from typing import List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import generate_embedding
from app.models.fact import Fact
from app.schemas.fact import FactCandidate

logger = logging.getLogger(__name__)

DEDUPE_THRESHOLD = 0.92


def fact_embedding_text(statement: str, detail: Optional[str]) -> str:
    """Facts embed statement + detail only (spec §1.2)."""
    return f"{statement}\n{detail}" if detail else statement


def _union(existing: Optional[List[str]], new: Optional[List[str]]) -> List[str]:
    return list(dict.fromkeys([*(existing or []), *(new or [])]))


def _source_entry(cand: FactCandidate) -> dict:
    return {
        "source_type": cand.source_type,
        "source_ref": cand.source_ref,
        "snippet": cand.source_snippet,
    }


async def _nearest(
    db: AsyncSession, user_id: str, embedding: List[float]
) -> Optional[Tuple[Fact, float]]:
    distance = Fact.embedding.cosine_distance(embedding)
    row = (await db.execute(
        select(Fact, (1 - distance).label("similarity"))
        .where(Fact.user_id == user_id, Fact.embedding.is_not(None))
        .order_by(distance)
        .limit(1)
    )).first()
    return (row[0], float(row[1])) if row else None


async def upsert_candidate_outcome(
    db: AsyncSession,
    user_id: str,
    cand: FactCandidate,
    auto_approve: bool = False,
) -> Tuple[Fact, str]:
    """Insert or merge one candidate; returns (fact, 'created' | 'merged' | 'auto_approved')."""
    embedding = await generate_embedding(fact_embedding_text(cand.statement, cand.detail))
    nearest = await _nearest(db, user_id, embedding)

    if nearest and nearest[1] >= DEDUPE_THRESHOLD:
        fact = nearest[0]
        fact.sources = [*(fact.sources or []), _source_entry(cand)]
        fact.skills = _union(fact.skills, cand.skills)
        fact.industries = _union(fact.industries, cand.industries)
        fact.job_types = _union(fact.job_types, list(cand.job_types))
        if fact.status != "approved" and cand.strength > fact.strength:
            # Unreviewed fact: keep the strongest wording. Approved wording is never touched.
            fact.statement = cand.statement
            fact.detail = cand.detail
            fact.embedding = embedding
        fact.strength = max(fact.strength, cand.strength)
        if auto_approve and fact.status == "candidate":
            fact.status = "approved"
        await db.flush()
        return fact, ("auto_approved" if fact.status == "approved" else "merged")

    fact = Fact(
        user_id=user_id,
        kind=cand.kind,
        statement=cand.statement,
        detail=cand.detail,
        skills=list(cand.skills),
        industries=list(cand.industries),
        job_types=list(cand.job_types),
        strength=cand.strength,
        status="approved" if auto_approve else "candidate",
        source_type=cand.source_type,
        source_ref=cand.source_ref,
        sources=[_source_entry(cand)],
        embedding=embedding,
    )
    db.add(fact)
    await db.flush()
    return fact, ("auto_approved" if auto_approve else "created")


async def upsert_candidate(
    db: AsyncSession,
    user_id: str,
    cand: FactCandidate,
    auto_approve: bool = False,
) -> Fact:
    fact, _ = await upsert_candidate_outcome(db, user_id, cand, auto_approve)
    return fact


async def search_facts(
    db: AsyncSession,
    user_id: str,
    query_embedding: List[float],
    limit: int = 8,
    status: str = "approved",
) -> List[Tuple[Fact, float]]:
    """Nearest facts by cosine similarity, most similar first."""
    distance = Fact.embedding.cosine_distance(query_embedding)
    rows = (await db.execute(
        select(Fact, (1 - distance).label("similarity"))
        .where(Fact.user_id == user_id, Fact.status == status, Fact.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )).all()
    return [(row[0], float(row[1])) for row in rows]


async def credit_facts(db: AsyncSession, fact_ids: List[str], won: bool) -> None:
    """won=False: the facts were used in a generated draft (times_used += 1).
    won=True: that draft got a reply/interview/hire (times_in_won += 1)."""
    if not fact_ids:
        return
    ids = [str(i) for i in fact_ids]
    stmt = update(Fact).where(Fact.id.in_(ids))
    if won:
        stmt = stmt.values(times_in_won=Fact.times_in_won + 1)
    else:
        stmt = stmt.values(times_used=Fact.times_used + 1)
    await db.execute(stmt.execution_options(synchronize_session=False))
```

- [ ] **Step 4: Run the test and confirm it passes**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_facts_service.py`
Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/services/facts.py api/tests/test_facts_service.py
git commit -m "$(cat <<'EOF'
feat(knowledge): facts service — dedupe/merge at 0.92, auto-approve, search, credit

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.5: Facts router with review, manual create, edit and bulk-approve

**Files:**
- Create: `api/app/api/v1/facts.py`
- Modify: `api/app/api/v1/__init__.py` (import after line 19; `include_router` after line 39)
- Create: `api/tests/test_facts_api.py`

**Interfaces:**
- Consumes: `upsert_candidate_outcome` and `fact_embedding_text` (Task 1.4); the schemas from Task 1.3.
- Produces these routes:
  - `GET /api/v1/facts?status=&kind=&limit=` returns `list[FactOut]`, ordered by kind, then strength descending, then newest.
  - `POST /api/v1/facts` with body `FactCreate` returns 201 `FactOut` with status `approved` and `source_type='manual'`.
  - `PATCH /api/v1/facts/{id}` with body `FactUpdate` returns `FactOut`. It re-embeds when `statement` or `detail` changes and returns 404 for a fact that is missing or belongs to another user.
  - `POST /api/v1/facts/bulk-approve` with body `{ids}` returns `{"approved": n}`.

- [ ] **Step 1: Write the failing test**

`api/tests/test_facts_api.py`:
```python
"""Integration tests for /api/v1/facts review endpoints (embeddings mocked)."""
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.models.fact import Fact
from tests.conftest import TestSessionLocal
from tests.vector_utils import make_fake_embedder, unit

BASE = "/api/v1/facts"


@pytest.fixture
def fake_embed():
    mock = make_fake_embedder()
    with patch("app.services.facts.generate_embedding", mock), \
         patch("app.api.v1.facts.generate_embedding", mock):
        yield mock


async def _user_id(client: AsyncClient, headers: dict) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


async def _seed_fact(user_id: str, statement: str, axis: int, **kw) -> str:
    async with TestSessionLocal() as s:
        fact = Fact(
            user_id=user_id, kind=kw.pop("kind", "metric"), statement=statement,
            status=kw.pop("status", "candidate"), strength=kw.pop("strength", 0.6),
            source_type="chatgpt_user_turn", source_ref="conv-1",
            sources=[{"source_type": "chatgpt_user_turn", "source_ref": "conv-1", "snippet": "quote"}],
            embedding=unit(1000 + axis), **kw,
        )
        s.add(fact)
        await s.commit()
        return fact.id


@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient):
    r = await client.get(BASE)
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_manual_fact_is_approved(client: AsyncClient, auth_headers: dict, fake_embed):
    r = await client.post(BASE, headers=auth_headers, json={
        "kind": "credential", "statement": "Holds an MBA.", "job_types": ["cto"],
    })
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "approved"
    assert body["source_type"] == "manual"
    assert body["job_types"] == ["cto"]
    fake_embed.assert_awaited_once_with("Holds an MBA.")


@pytest.mark.asyncio
async def test_list_filters_by_status_and_kind(client: AsyncClient, auth_headers: dict):
    uid = await _user_id(client, auth_headers)
    await _seed_fact(uid, "Candidate metric", 1)
    await _seed_fact(uid, "Approved metric", 2, status="approved")
    await _seed_fact(uid, "Candidate project", 3, kind="project")

    r = await client.get(BASE, headers=auth_headers, params={"status": "candidate"})
    assert sorted(f["statement"] for f in r.json()) == ["Candidate metric", "Candidate project"]

    r = await client.get(BASE, headers=auth_headers, params={"status": "candidate", "kind": "project"})
    assert [f["statement"] for f in r.json()] == ["Candidate project"]
    assert r.json()[0]["sources"][0]["snippet"] == "quote"


@pytest.mark.asyncio
async def test_patch_edits_reembeds_and_rejects(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _user_id(client, auth_headers)
    fid = await _seed_fact(uid, "Old wording", 4)

    r = await client.patch(f"{BASE}/{fid}", headers=auth_headers, json={"statement": "New wording"})
    assert r.status_code == 200
    assert r.json()["statement"] == "New wording"
    fake_embed.assert_awaited_once_with("New wording")

    r = await client.patch(f"{BASE}/{fid}", headers=auth_headers, json={"status": "rejected"})
    assert r.json()["status"] == "rejected"
    assert fake_embed.await_count == 1  # status-only change does not re-embed

    r = await client.get(BASE, headers=auth_headers, params={"status": "rejected"})
    assert [f["id"] for f in r.json()] == [fid]


@pytest.mark.asyncio
async def test_patch_other_users_fact_404(client: AsyncClient, auth_headers: dict):
    uid = await _user_id(client, auth_headers)
    fid = await _seed_fact(uid, "Mine", 5)
    other = await client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "testpass123"})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    r = await client.patch(f"{BASE}/{fid}", headers=other_headers, json={"status": "approved"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_bulk_approve(client: AsyncClient, auth_headers: dict):
    uid = await _user_id(client, auth_headers)
    a = await _seed_fact(uid, "A", 6)
    b = await _seed_fact(uid, "B", 7)
    await _seed_fact(uid, "C", 8)

    r = await client.post(f"{BASE}/bulk-approve", headers=auth_headers, json={"ids": [a, b]})
    assert r.status_code == 200
    assert r.json() == {"approved": 2}

    r = await client.get(BASE, headers=auth_headers, params={"status": "candidate"})
    assert [f["statement"] for f in r.json()] == ["C"]
```

- [ ] **Step 2: Run the test and confirm it fails**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_facts_api.py`
Expected: FAIL. Tests that use `fake_embed` error with `ModuleNotFoundError: No module named 'app.api.v1.facts'`, raised by `patch("app.api.v1.facts.generate_embedding")`. The remaining tests fail because the routes return 404.

- [ ] **Step 3: Implement**

`api/app/api/v1/facts.py`:
```python
"""Facts (knowledge layer) endpoints: review queue, manual facts, ingestion."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.embeddings import generate_embedding
from app.core.security import get_current_user
from app.models.fact import Fact
from app.models.user import User
from app.schemas.fact import (
    FactBulkApprove,
    FactCandidate,
    FactCreate,
    FactKind,
    FactOut,
    FactStatus,
    FactUpdate,
)
from app.services.facts import fact_embedding_text, upsert_candidate_outcome

router = APIRouter()


@router.get("", response_model=List[FactOut])
async def list_facts(
    status_filter: Optional[FactStatus] = Query(None, alias="status"),
    kind: Optional[FactKind] = None,
    limit: int = Query(500, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List facts for review (grouped client-side by kind)."""
    query = select(Fact).where(Fact.user_id == current_user.id)
    if status_filter:
        query = query.where(Fact.status == status_filter)
    if kind:
        query = query.where(Fact.kind == kind)
    query = query.order_by(Fact.kind, Fact.strength.desc(), Fact.created_at.desc()).limit(limit)
    return (await db.execute(query)).scalars().all()


@router.post("", response_model=FactOut, status_code=status.HTTP_201_CREATED)
async def create_fact(
    data: FactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a manual fact. The user typed it, so it is approved (merged if a near-duplicate exists)."""
    cand = FactCandidate(source_type="manual", **data.model_dump())
    fact, _ = await upsert_candidate_outcome(db, current_user.id, cand, auto_approve=True)
    fact.status = "approved"
    await db.commit()
    await db.refresh(fact)
    return fact


@router.patch("/{fact_id}", response_model=FactOut)
async def update_fact(
    fact_id: str,
    data: FactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit / approve / reject a fact."""
    fact = (await db.execute(
        select(Fact).where(Fact.id == fact_id, Fact.user_id == current_user.id)
    )).scalar_one_or_none()
    if not fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(fact, field, value)
    if "statement" in update_data or "detail" in update_data:
        fact.embedding = await generate_embedding(fact_embedding_text(fact.statement, fact.detail))

    await db.commit()
    await db.refresh(fact)
    return fact


@router.post("/bulk-approve")
async def bulk_approve_facts(
    request: FactBulkApprove,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not request.ids:
        return {"approved": 0}
    result = await db.execute(
        update(Fact)
        .where(Fact.user_id == current_user.id, Fact.id.in_(request.ids))
        .values(status="approved")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return {"approved": result.rowcount}
```

`api/app/api/v1/__init__.py`: after line 19 (`from app.api.v1.admin import router as admin_router`) add:
```python
from app.api.v1.facts import router as facts_router
```
After line 39 (the `admin_router` include) add:
```python
router.include_router(facts_router, prefix="/facts", tags=["Facts"])
```

- [ ] **Step 4: Run the test and confirm it passes**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_facts_api.py`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/api/v1/facts.py api/app/api/v1/__init__.py api/tests/test_facts_api.py
git commit -m "$(cat <<'EOF'
feat(knowledge): /facts router — list, manual create, edit/approve/reject, bulk-approve

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.6: Ingest endpoints `/facts/ingest`, `/facts/from-memories` and `/facts/from-proposals`

**Files:**
- Modify: `api/app/services/facts.py` (imports at the top; append `ingest_items` and `_already_ingested`)
- Modify: `api/app/api/v1/facts.py` (imports; append three routes)
- Create: `api/tests/test_facts_ingest_api.py`

**Interfaces:**
- Consumes: `extract_facts` (Task 1.3) and `upsert_candidate_outcome` (Task 1.4).
- Produces: `async ingest_items(db, user_id, source_type: str, items: list[FactIngestItem], auto_approve=False) -> dict` with keys `created, merged, auto_approved, skipped, failed` plus `failed_refs` (source_refs whose extraction raised; not part of `FactIngestResult`). Items are skipped when a fact already lists `{source_type, source_ref}` in `sources`, which makes re-runs cheap and idempotent. Extraction runs concurrently and upserts run sequentially.
- Routes:
  - `POST /api/v1/facts/ingest` with body `FactIngestRequest` returns `FactIngestResult`.
  - `POST /api/v1/facts/from-memories` returns `FactIngestResult`. It converts bio memories into facts with `source_type='bio_memory'`, auto-approved. Bio memories are those with `importance_score >= 0.9`, not excluded, not `JOB POSTING:` and not `category='lesson'`.
  - `POST /api/v1/facts/from-proposals?limit=10` returns `FactIngestResult`. It processes voice samples with `author IN ('chris','chris_edited_ai')` that have letter text and `facts_ingested_at IS NULL`, and stamps `facts_ingested_at` on every processed proposal whose extraction did not raise (zero-fact letters included), so the queue always advances. It uses `source_type='upwork_proposal'` and `source_ref=proposals.id`. The letter and screening answers form the extraction text, and the job title and text go in as context. The response includes `remaining`.
- Contract addition: the `from-proposals` route is new. Spec §1.3.2 requires fact candidates from submitted Upwork letters.

- [ ] **Step 1: Write the failing test**

`api/tests/test_facts_ingest_api.py`:
```python
"""Integration tests for fact ingestion endpoints (extraction + embeddings mocked)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.memory import Memory
from app.models.proposal import Proposal
from app.schemas.fact import FactCandidate
from tests.conftest import TestSessionLocal
from tests.vector_utils import make_fake_embedder

BASE = "/api/v1/facts"


async def _fake_extract(text, source_type, source_ref=None, context=None):
    """Same statement for every item -> second item dedupes into the first."""
    return [FactCandidate(
        kind="metric", statement="Cut cloud spend 38% for a fintech client.", strength=0.8,
        source_type=source_type, source_ref=source_ref, source_snippet="cut spend 38%",
    )]


async def _per_ref_extract(text, source_type, source_ref=None, context=None):
    """Distinct statement per source_ref -> no dedupe."""
    return [FactCandidate(
        kind="project", statement=f"Fact from {source_ref}", strength=0.7,
        source_type=source_type, source_ref=source_ref,
    )]


@pytest.fixture
def fake_embed():
    mock = make_fake_embedder()
    with patch("app.services.facts.generate_embedding", mock):
        yield mock


async def _user_id(client, headers) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


@pytest.mark.asyncio
async def test_ingest_creates_merges_and_is_idempotent(client: AsyncClient, auth_headers: dict, fake_embed):
    extract = AsyncMock(side_effect=_fake_extract)
    payload = {
        "source_type": "chatgpt_user_turn",
        "items": [
            {"text": "We cut spend 38%", "source_ref": "conv-1", "context": "letter"},
            {"text": "Again: 38% cut", "source_ref": "conv-2"},
        ],
    }
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/ingest", headers=auth_headers, json=payload)
        assert r.status_code == 200
        assert r.json() == {"created": 1, "merged": 1, "auto_approved": 0, "skipped": 0, "failed": 0, "remaining": 0}

        r = await client.post(f"{BASE}/ingest", headers=auth_headers, json=payload)
        assert r.json()["skipped"] == 2
    assert extract.await_count == 2  # second run never re-extracts

    facts = (await client.get(BASE, headers=auth_headers, params={"status": "candidate"})).json()
    assert len(facts) == 1
    assert [s["source_ref"] for s in facts[0]["sources"]] == ["conv-1", "conv-2"]


@pytest.mark.asyncio
async def test_ingest_counts_extraction_failures(client: AsyncClient, auth_headers: dict, fake_embed):
    extract = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/ingest", headers=auth_headers, json={
            "source_type": "chatgpt_user_turn", "items": [{"text": "x", "source_ref": "c"}],
        })
    assert r.json()["failed"] == 1


@pytest.mark.asyncio
async def test_from_memories_uses_only_bio_memories_and_auto_approves(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        bio = Memory(user_id=uid, title="Stratavault.ai", content="Built Stratavault.ai", category="project", importance_score=1.0)
        s.add_all([
            bio,
            Memory(user_id=uid, title="Style", content="Prefers terse tone", category="lesson", importance_score=0.95),
            Memory(user_id=uid, title="Past Proposal", content="JOB POSTING:\nNeed dev", importance_score=0.9, exclude_from_retrieval=True),
            Memory(user_id=uid, title="Minor", content="Knows Excel", category="skill_demo", importance_score=0.5),
        ])
        await s.commit()
        bio_id = bio.id

    extract = AsyncMock(side_effect=_per_ref_extract)
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/from-memories", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["auto_approved"] == 1
    assert [c.args[2] for c in extract.await_args_list] == [bio_id]  # (text, source_type, source_ref, context)

    approved = (await client.get(BASE, headers=auth_headers, params={"status": "approved"})).json()
    assert [f["statement"] for f in approved] == [f"Fact from {bio_id}"]
    assert approved[0]["source_type"] == "bio_memory"


@pytest.mark.asyncio
async def test_from_proposals_marks_zero_fact_letters_and_retries_failures(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        s.add_all([
            Proposal(user_id=uid, cover_letter_text="Short thanks note", job_title="J1", source="scraped"),
            Proposal(user_id=uid, cover_letter_text="Letter that errors", job_title="J2", source="scraped"),
        ])
        await s.commit()

    async def _extract(text, source_type, source_ref=None, context=None):
        if "errors" in text:
            raise RuntimeError("haiku down")
        return []

    extract = AsyncMock(side_effect=_extract)
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers, params={"limit": 10})
        assert r.json()["failed"] == 1
        assert r.json()["remaining"] == 1  # the failed one only
        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers, params={"limit": 10})
    texts = [c.args[0] for c in extract.await_args_list]
    assert texts.count("Short thanks note") == 1  # zero-fact letter never re-extracted
    assert texts.count("Letter that errors") == 2  # failure retried


@pytest.mark.asyncio
async def test_from_proposals_batches_and_skips_ai_authored(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        s.add_all([
            Proposal(user_id=uid, cover_letter_text="Letter one", job_title="Job 1", job_text="Need SQL",
                     screening_answers=[{"question": "Experience?", "answer": "20 years"}], source="scraped"),
            Proposal(user_id=uid, cover_letter_text="Letter two", job_title="Job 2", source="scraped"),
            Proposal(user_id=uid, cover_letter_text="Letter three", job_title="Job 3", source="extension", author="chris_edited_ai"),
            Proposal(user_id=uid, cover_letter_text="ChatGPT letter", source="chatgpt_import", author="ai"),
            Proposal(user_id=uid, cover_letter_text="", job_title="Empty", source="scraped"),
        ])
        await s.commit()

    extract = AsyncMock(side_effect=_per_ref_extract)
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers, params={"limit": 2})
        assert r.json()["created"] == 2
        assert r.json()["remaining"] == 1

        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers, params={"limit": 2})
        assert r.json()["created"] == 1
        assert r.json()["remaining"] == 0

        r = await client.post(f"{BASE}/from-proposals", headers=auth_headers, params={"limit": 2})
        assert r.json()["remaining"] == 0
    assert extract.await_count == 3  # nothing is re-extracted once processed

    texts = [c.args[0] for c in extract.await_args_list]
    assert len(texts) == 3
    assert not any("ChatGPT letter" in t for t in texts)
    assert any("Q: Experience?" in t and "A: 20 years" in t for t in texts)
    assert all(c.args[1] == "upwork_proposal" for c in extract.await_args_list)
```

- [ ] **Step 2: Run the test and confirm it fails**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_facts_ingest_api.py`
Expected: FAIL with `AttributeError: <module 'app.services.facts'> does not have the attribute 'extract_facts'`.

- [ ] **Step 3: Implement**

In `api/app/services/facts.py`, replace the import block with:
```python
import asyncio
import logging
from typing import List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import generate_embedding
from app.models.fact import Fact
from app.schemas.fact import FactCandidate, FactIngestItem
from app.services.fact_extraction import extract_facts
```
Append:
```python
async def _already_ingested(db: AsyncSession, user_id: str, source_type: str, source_ref: str) -> bool:
    row = await db.execute(
        select(Fact.id)
        .where(
            Fact.user_id == user_id,
            Fact.sources.contains([{"source_type": source_type, "source_ref": source_ref}]),
        )
        .limit(1)
    )
    return row.first() is not None


async def ingest_items(
    db: AsyncSession,
    user_id: str,
    source_type: str,
    items: List[FactIngestItem],
    auto_approve: bool = False,
) -> dict:
    """Extract candidates from each item and upsert them. Items whose source_ref already
    appears in a fact's sources are skipped, so re-runs only pay for new material."""
    counts = {"created": 0, "merged": 0, "auto_approved": 0, "skipped": 0, "failed": 0}
    failed_refs: List[Optional[str]] = []

    pending: List[FactIngestItem] = []
    for item in items:
        if item.source_ref and await _already_ingested(db, user_id, source_type, item.source_ref):
            counts["skipped"] += 1
        else:
            pending.append(item)

    results = await asyncio.gather(
        *(extract_facts(i.text, source_type, i.source_ref, i.context) for i in pending),
        return_exceptions=True,
    )
    for item, result in zip(pending, results):
        if isinstance(result, BaseException):
            logger.warning("Fact extraction failed for %s/%s: %s", source_type, item.source_ref, result)
            counts["failed"] += 1
            failed_refs.append(item.source_ref)
            continue
        for cand in result:
            _, outcome = await upsert_candidate_outcome(db, user_id, cand, auto_approve)
            counts[outcome] += 1
    # Not a FactIngestResult field (pydantic ignores it); /from-proposals uses it to leave
    # failed letters unmarked so they are retried.
    counts["failed_refs"] = failed_refs
    return counts
```

In `api/app/api/v1/facts.py`, replace the import block with:
```python
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.embeddings import generate_embedding
from app.core.security import get_current_user
from app.models.fact import Fact
from app.models.memory import Memory
from app.models.proposal import Proposal
from app.models.user import User
from app.schemas.fact import (
    FactBulkApprove,
    FactCandidate,
    FactCreate,
    FactIngestItem,
    FactIngestRequest,
    FactIngestResult,
    FactKind,
    FactOut,
    FactStatus,
    FactUpdate,
)
from app.services.facts import fact_embedding_text, ingest_items, upsert_candidate_outcome
```
Append these routes:
```python
@router.post("/ingest", response_model=FactIngestResult)
async def ingest_facts(
    request: FactIngestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract fact candidates from user-written text (used by scripts/ingest_chatgpt_facts.py)."""
    counts = await ingest_items(
        db, current_user.id, request.source_type, request.items, request.auto_approve
    )
    await db.commit()
    return FactIngestResult(**counts)


@router.post("/from-memories", response_model=FactIngestResult)
async def facts_from_memories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Split curated bio memories into atomic facts, auto-approved (spec §1.3.4)."""
    memories = (await db.execute(
        select(Memory).where(
            Memory.user_id == current_user.id,
            Memory.exclude_from_retrieval.is_(False),
            Memory.importance_score >= 0.9,
            ~Memory.content.like("JOB POSTING:%"),
            or_(Memory.category.is_(None), Memory.category != "lesson"),
        )
    )).scalars().all()
    items = [
        FactIngestItem(
            text=f"{m.title}\n{m.content}" + (f"\nOutcome: {m.outcome}" if m.outcome else ""),
            source_ref=m.id,
        )
        for m in memories
    ]
    counts = await ingest_items(db, current_user.id, "bio_memory", items, auto_approve=True)
    await db.commit()
    return FactIngestResult(**counts)


def _proposal_source_text(p: Proposal) -> str:
    parts = [p.cover_letter_text.strip()]
    for qa in p.screening_answers or []:
        parts.append(f"Q: {qa.get('question', '')}\nA: {qa.get('answer', '')}")
    return "\n\n".join(parts)


@router.post("/from-proposals", response_model=FactIngestResult)
async def facts_from_proposals(
    limit: int = Query(10, ge=1, le=25),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fact candidates from submitted letters + answers (spec §1.3.2). Call repeatedly until remaining == 0."""
    pending = (await db.execute(
        select(Proposal)
        .where(
            Proposal.user_id == current_user.id,
            Proposal.author.in_(("chris", "chris_edited_ai")),
            Proposal.cover_letter_text != "",
            Proposal.facts_ingested_at.is_(None),
        )
        .order_by(Proposal.submitted_at.desc().nullslast(), Proposal.created_at.desc())
    )).scalars().all()
    batch = pending[:limit]

    items = [
        FactIngestItem(
            text=_proposal_source_text(p),
            source_ref=p.id,
            context=f"Job: {p.job_title or ''}\n{(p.job_text or '')[:1500]}".strip(),
        )
        for p in batch
    ]
    counts = await ingest_items(db, current_user.id, "upwork_proposal", items)
    failed = set(counts["failed_refs"])
    now = datetime.now(timezone.utc)
    for p in batch:
        if p.id not in failed:
            p.facts_ingested_at = now  # zero-fact letters too, so the next call moves on
    await db.commit()
    return FactIngestResult(**counts, remaining=len(pending) - len(batch) + len(failed))
```

A proposal whose extraction raised stays unmarked and counts toward `remaining`, so the next call retries it; one that yielded zero facts is marked and never re-extracted.

- [ ] **Step 4: Run the tests and confirm they pass**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_facts_ingest_api.py tests/test_facts_api.py tests/test_facts_service.py`
Expected: `21 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/services/facts.py api/app/api/v1/facts.py api/tests/test_facts_ingest_api.py
git commit -m "$(cat <<'EOF'
feat(knowledge): fact ingestion — /facts/ingest, /from-memories (auto-approved), /from-proposals

Idempotent by (source_type, source_ref) recorded in facts.sources.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.7: Exclude flagged memories from `job_analysis` retrieval

**Files:**
- Modify: `api/app/services/job_analysis.py` (line 234 in `find_relevant_memories_with_embedding`)
- Create: `api/tests/test_memory_retrieval_exclusion.py`

**Interfaces:**
- Consumes: `Memory.exclude_from_retrieval` (Task 1.1).
- Produces: `find_relevant_memories_with_embedding` (unchanged signature) now ignores excluded rows. The user-facing `/memories/search` endpoint is intentionally left alone.

- [ ] **Step 1: Write the failing test**

`api/tests/test_memory_retrieval_exclusion.py`:
```python
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
```

- [ ] **Step 2: Run the test and confirm it fails**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_memory_retrieval_exclusion.py`
Expected: FAIL with `AssertionError: assert ['Bio', 'Past Proposal: X'] == ['Bio']` (the order of the two equal-similarity rows may vary).

- [ ] **Step 3: Implement**

In `api/app/services/job_analysis.py`, inside the SQL of `find_relevant_memories_with_embedding` (lines 233-234):
```python
        WHERE user_id = :user_id
        AND embedding IS NOT NULL
```
becomes
```python
        WHERE user_id = :user_id
        AND embedding IS NOT NULL
        AND NOT exclude_from_retrieval
```
Make this change only in the memories query at line 234. Leave the proposals query near line 780 untouched.

- [ ] **Step 4: Run the test and confirm it passes, then run the analysis tests**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_memory_retrieval_exclusion.py tests/test_job_analysis.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/services/job_analysis.py api/tests/test_memory_retrieval_exclusion.py
git commit -m "$(cat <<'EOF'
fix(retrieval): skip exclude_from_retrieval memories (corpus job posts) in job analysis

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.8: `import-from-upwork` stores full voice samples

**Files:**
- Modify: `api/app/schemas/proposal.py` (`ProposalResponse`, lines 39-63: add four fields after `source`)
- Modify: `api/app/api/v1/proposals.py` (insert helpers before line 481; replace the `import_proposals_from_upwork` body, lines 481-567)
- Create: `api/tests/test_proposals_import.py`

**Interfaces:**
- Consumes: the Proposal voice-sample columns (Task 1.1).
- The raw payload accepts the existing keys plus these new optional keys, which the Task 1.10 scraper sends:
  - `screeningAnswers: [{question, answer}]`
  - `jobDescription: str`
  - `outcome: str`, accepted when it is in the outcome set; otherwise it is derived from `wasHired` and the status.
  - `author: str`, defaulting to `chris`.
- `ProposalResponse` gains `author`, `outcome`, `job_text` and `screening_answers`.
- Re-importing an existing `proposalId` now backfills the longer letter, answers, job text, `job_needs_embedding` and the fresher outcome. The endpoint still returns only newly created rows.
- New rows get `job_needs_embedding = embed(title + job description)`.

- [ ] **Step 1: Write the failing test**

`api/tests/test_proposals_import.py`:
```python
"""import-from-upwork captures full voice samples (letter + answers + job text + outcome)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.proposal import Proposal
from tests.conftest import TestSessionLocal
from tests.vector_utils import unit

URL = "/api/v1/proposals/import-from-upwork"


@pytest.fixture
def fake_embed():
    mock = AsyncMock(return_value=unit(3))
    with patch("app.api.v1.proposals.generate_embedding", mock):
        yield mock


async def _row(upwork_id: str) -> Proposal:
    async with TestSessionLocal() as s:
        return (await s.execute(select(Proposal).where(Proposal.upwork_proposal_id == upwork_id))).scalar_one()


@pytest.mark.asyncio
async def test_import_stores_answers_job_text_and_outcome(client: AsyncClient, auth_headers: dict, fake_embed):
    r = await client.post(URL, headers=auth_headers, json={"proposals": [{
        "proposalId": "111", "jobTitle": "Azure SQL migration", "coverLetter": "Full letter text",
        "status": "archived", "wasHired": True, "jobDescription": "Move our SQL estate to Azure",
        "screeningAnswers": [
            {"question": "Similar projects?", "answer": "160-server migration"},
            {"question": "Empty", "answer": "  "},
        ],
    }]})
    assert r.status_code == 200
    body = r.json()[0]
    assert body["author"] == "chris"
    assert body["outcome"] == "hired"
    assert body["job_text"] == "Move our SQL estate to Azure"
    assert body["screening_answers"] == [{"question": "Similar projects?", "answer": "160-server migration"}]

    row = await _row("111")
    assert row.job_needs_embedding is not None
    texts = [c.args[0] for c in fake_embed.await_args_list]
    assert "Azure SQL migration\n\nMove our SQL estate to Azure" in texts


@pytest.mark.asyncio
async def test_outcome_derivation_and_author_validation(client: AsyncClient, auth_headers: dict, fake_embed):
    r = await client.post(URL, headers=auth_headers, json={"proposals": [
        {"proposalId": "201", "jobTitle": "A", "coverLetter": "x", "status": "interviewed"},
        {"proposalId": "202", "jobTitle": "B", "coverLetter": "x", "status": "responded", "author": "chris_edited_ai"},
        {"proposalId": "203", "jobTitle": "C", "coverLetter": "x", "status": "submitted", "author": "robot"},
        {"proposalId": "204", "jobTitle": "D", "coverLetter": "x", "status": "submitted", "outcome": "declined"},
    ]})
    by_id = {p["upwork_proposal_id"]: p for p in r.json()}
    assert by_id["201"]["outcome"] == "interviewed"
    assert by_id["202"]["outcome"] == "replied"
    assert by_id["202"]["author"] == "chris_edited_ai"
    assert by_id["203"]["author"] == "chris"
    assert by_id["203"]["outcome"] is None
    assert by_id["204"]["outcome"] == "declined"


@pytest.mark.asyncio
async def test_reimport_backfills_existing_row(client: AsyncClient, auth_headers: dict, fake_embed):
    await client.post(URL, headers=auth_headers, json={"proposals": [
        {"proposalId": "301", "jobTitle": "Old", "coverLetter": "short", "status": "submitted"},
    ]})
    r = await client.post(URL, headers=auth_headers, json={"proposals": [{
        "proposalId": "301", "jobTitle": "Old", "coverLetter": "short letter, now complete",
        "status": "interviewed", "jobDescription": "Need a fractional CTO",
        "screeningAnswers": [{"question": "Q1", "answer": "A1"}],
    }]})
    assert r.json() == []  # nothing newly created

    row = await _row("301")
    assert row.cover_letter_text == "short letter, now complete"
    assert row.screening_answers == [{"question": "Q1", "answer": "A1"}]
    assert row.job_text == "Need a fractional CTO"
    assert row.outcome == "interviewed"
    assert row.job_needs_embedding is not None
```

- [ ] **Step 2: Run the test and confirm it fails**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_proposals_import.py`
Expected: FAIL with `KeyError: 'author'` (the response has no such field), and the backfill test fails on `screening_answers`.

- [ ] **Step 3: Implement**

In `api/app/schemas/proposal.py`, inside `ProposalResponse`, after `source: str` add:
```python
    author: str = "chris"
    outcome: Optional[str] = None
    job_text: Optional[str] = None
    screening_answers: Optional[List[dict]] = None
```

In `api/app/api/v1/proposals.py`, insert before `@router.post("/import-from-upwork", ...)` (line 481):
```python
VOICE_AUTHORS = {"chris", "chris_edited_ai", "ai"}
VOICE_OUTCOMES = {"no_response", "viewed", "replied", "interviewed", "hired", "declined"}


def _derive_outcome(raw_outcome: Optional[str], status_str: Optional[str], was_hired: bool) -> Optional[str]:
    """Map scraper status onto the voice-sample outcome enum (None = unknown yet)."""
    if raw_outcome in VOICE_OUTCOMES:
        return raw_outcome
    if was_hired:
        return "hired"
    s = (status_str or "").lower()
    if "interview" in s:
        return "interviewed"
    if s in ("responded", "active"):
        return "replied"
    if "declin" in s:
        return "declined"
    return None


def _clean_answers(raw) -> Optional[list]:
    if not isinstance(raw, list):
        return None
    answers = [
        {"question": str(a.get("question") or "").strip(), "answer": str(a.get("answer") or "").strip()}
        for a in raw
        if isinstance(a, dict) and str(a.get("answer") or "").strip()
    ]
    return answers or None


async def _job_needs_embedding(job_title: Optional[str], job_text: Optional[str]) -> Optional[List[float]]:
    """Embedding of the JOB (not the letter) so voice-sample retrieval is job<->job."""
    text_for_embedding = "\n\n".join(t for t in (job_title, job_text) if t)
    if not text_for_embedding:
        return None
    try:
        return await generate_embedding(text_for_embedding)
    except Exception:
        return None
```

Replace the whole `import_proposals_from_upwork` function (lines 481-567) with:
```python
@router.post("/import-from-upwork", response_model=List[ProposalResponse])
async def import_proposals_from_upwork(
    request: ProposalImportFromUpwork,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import proposals scraped from Upwork (list + detail pages) as voice samples.

    New rows are created; existing rows (same proposalId) are backfilled with the full
    letter, screening answers, job text and the latest outcome. Returns created rows only.
    """
    created_proposals = []

    for raw_data in request.proposals:
        upwork_proposal_id = raw_data.get("proposalId")
        cover_letter_text = (raw_data.get("coverLetter") or "").strip()
        job_title = raw_data.get("jobTitle")
        job_url = raw_data.get("jobUrl")
        bid_amount = raw_data.get("bidAmount")
        bid_type = raw_data.get("bidType")
        status_str = raw_data.get("status", "submitted")
        submitted_at_str = raw_data.get("submittedAt")
        screening_answers = _clean_answers(raw_data.get("screeningAnswers"))
        job_text = (raw_data.get("jobDescription") or "").strip() or None
        author = raw_data.get("author") if raw_data.get("author") in VOICE_AUTHORS else "chris"

        # Require at least a job title to import
        if not job_title:
            continue

        # Allow explicit wasHired override from the scraper (e.g. archived proposals
        # whose status string doesn't say "hired" but the scraper detected a contract)
        was_hired_override = raw_data.get("wasHired")
        if was_hired_override is not None:
            was_hired = bool(was_hired_override)
        else:
            was_hired = status_str == "hired"
        outcome = _derive_outcome(raw_data.get("outcome"), status_str, was_hired)

        if upwork_proposal_id:
            existing = (await db.execute(
                select(Proposal).where(
                    Proposal.upwork_proposal_id == upwork_proposal_id,
                    Proposal.user_id == current_user.id,
                )
            )).scalar_one_or_none()
            if existing:
                if cover_letter_text and len(cover_letter_text) > len(existing.cover_letter_text or ""):
                    existing.cover_letter_text = cover_letter_text
                    existing.embedding = await generate_embedding(f"Job: {job_title}\n\n{cover_letter_text}")
                    existing.facts_ingested_at = None  # new text -> eligible for /facts/from-proposals again
                if screening_answers and screening_answers != existing.screening_answers:
                    existing.screening_answers = screening_answers
                    existing.facts_ingested_at = None
                if job_text and not existing.job_text:
                    existing.job_text = job_text
                if existing.job_needs_embedding is None:
                    existing.job_needs_embedding = await _job_needs_embedding(job_title, existing.job_text)
                if outcome:
                    existing.outcome = outcome
                continue

        # Parse submitted_at — try ISO first, then "Mar 3, 2026" format
        submitted_at = None
        if submitted_at_str:
            try:
                submitted_at = datetime.fromisoformat(submitted_at_str.replace("Z", "+00:00"))
            except Exception:
                try:
                    submitted_at = datetime.strptime(submitted_at_str, "%b %d, %Y")
                except Exception:
                    pass

        # Letter embedding (legacy search) + job embedding (voice-sample retrieval)
        text_for_embedding = f"Job: {job_title}\n\n{cover_letter_text}".strip()
        embedding = await generate_embedding(text_for_embedding)

        proposal = Proposal(
            user_id=current_user.id,
            upwork_proposal_id=upwork_proposal_id,
            upwork_job_url=job_url,
            cover_letter_text=cover_letter_text,
            job_title=job_title,
            bid_amount=bid_amount,
            bid_type=bid_type,
            status=status_str,
            client_responded=status_str in ("responded", "interviewed", "hired"),
            was_hired=was_hired,
            submitted_at=submitted_at,
            source="scraped",
            embedding=embedding,
            author=author,
            outcome=outcome,
            job_text=job_text,
            screening_answers=screening_answers,
            job_needs_embedding=await _job_needs_embedding(job_title, job_text),
        )

        db.add(proposal)
        created_proposals.append(proposal)

    await db.commit()

    for proposal in created_proposals:
        await db.refresh(proposal)

    return created_proposals
```

- [ ] **Step 4: Run the tests and confirm they pass**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_proposals_import.py`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/schemas/proposal.py api/app/api/v1/proposals.py api/tests/test_proposals_import.py
git commit -m "$(cat <<'EOF'
feat(voice): import-from-upwork stores screening answers, job text, outcome, author + job embedding

Re-import backfills existing rows so earlier scrapes gain answers and job context.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.9: `scripts/ingest_chatgpt_facts.py`, a ChatGPT export → `/facts/ingest` script

**Files:**
- Create: `scripts/ingest_chatgpt_facts.py`
- Create: `api/tests/test_ingest_chatgpt_facts_script.py`

**Interfaces:**
- Consumes: `POST /api/v1/facts/ingest` (Task 1.6).
- Produces this CLI:
  ```
  python scripts/ingest_chatgpt_facts.py [EXPORT_DIR] --email E [--api URL] [--batch-size 5] [--limit N] [--dry-run]
  ```
  - `EXPORT_DIR` defaults to `/Users/admin/dev2/UpApply/working/chatgpt-export`.
  - The password comes from `UPAPPLY_PASSWORD` or a prompt, never from argv.
  - Functions: `load_conversations(dir)`, `conversation_messages(conv)`, `chunk_text(text, size)`, `build_items(conv)`, `main(argv)`.
- Behaviour:
  - It follows the active branch (`current_node` → root) and reads both `conversations.json` and `conversations-*.json`.
  - The joined user turns are the source text, chunked at 12,000 characters.
  - The last assistant message goes into the context only, capped at 4,000 characters and prefixed by the conversation title.
  - `source_type='chatgpt_user_turn'`. `source_ref` is the conversation id, or `id#n` when the text is chunked.

- [ ] **Step 1: Write the failing test**

`api/tests/test_ingest_chatgpt_facts_script.py`:
```python
"""Unit tests for scripts/ingest_chatgpt_facts.py (no network)."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ingest_chatgpt_facts.py"
spec = importlib.util.spec_from_file_location("ingest_chatgpt_facts", SCRIPT)
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)


def _node(nid, parent, role, text, children=()):
    return {
        "id": nid, "parent": parent, "children": list(children),
        "message": None if role is None else {"author": {"role": role}, "content": {"parts": [text]}},
    }


def _conv(conv_id="conv-1", title="Azure proposal"):
    mapping = {
        "root": _node("root", None, None, "", ["u1"]),
        "u1": _node("u1", "root", "user", "Here is the job post. I migrated 120 servers.", ["a1"]),
        "a1": _node("a1", "u1", "assistant", "Draft letter v1", ["u2", "u2-alt"]),
        "u2": _node("u2", "a1", "user", "Correction: it was 160 servers, not 120.", ["a2"]),
        "u2-alt": _node("u2-alt", "a1", "user", "ABANDONED BRANCH", []),
        "a2": _node("a2", "u2", "assistant", "Final letter mentioning 160 servers", []),
    }
    return {"id": conv_id, "title": title, "current_node": "a2", "mapping": mapping}


def test_conversation_messages_follows_active_branch():
    msgs = ingest.conversation_messages(_conv())
    assert [r for r, _ in msgs] == ["user", "assistant", "user", "assistant"]
    assert all("ABANDONED" not in t for _, t in msgs)


def test_build_items_uses_user_turns_as_text_and_last_assistant_as_context():
    items = ingest.build_items(_conv())
    assert len(items) == 1
    item = items[0]
    assert item["source_ref"] == "conv-1"
    assert "160 servers, not 120" in item["text"]
    assert "Draft letter" not in item["text"]
    assert "Final letter" not in item["text"]
    assert "Final letter mentioning 160 servers" in item["context"]
    assert "Azure proposal" in item["context"]


def test_build_items_skips_short_or_idless_conversations():
    short = _conv()
    short["mapping"]["u1"]["message"]["content"]["parts"] = ["hi"]
    short["mapping"]["u2"]["message"]["content"]["parts"] = ["ok"]
    assert ingest.build_items(short) == []
    no_id = _conv()
    no_id.pop("id")
    assert ingest.build_items(no_id) == []


def test_chunking_produces_suffixed_refs(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_SOURCE_CHARS", 60)
    conv = _conv()
    conv["mapping"]["u1"]["message"]["content"]["parts"] = ["A" * 50]
    conv["mapping"]["u2"]["message"]["content"]["parts"] = ["B" * 50]
    refs = [i["source_ref"] for i in ingest.build_items(conv)]
    assert refs == ["conv-1#1", "conv-1#2"]


def test_chunk_text_hard_splits_oversized_paragraph():
    chunks = ingest.chunk_text("x" * 25, 10)
    assert chunks == ["x" * 10, "x" * 10, "x" * 5]


def test_load_conversations_reads_both_layouts(tmp_path):
    (tmp_path / "conversations.json").write_text(json.dumps([_conv("a")]))
    assert [c["id"] for c in ingest.load_conversations(tmp_path)] == ["a"]
    split = tmp_path / "split"
    split.mkdir()
    (split / "conversations-000.json").write_text(json.dumps([_conv("b")]))
    (split / "conversations-001.json").write_text(json.dumps([_conv("c")]))
    assert [c["id"] for c in ingest.load_conversations(split)] == ["b", "c"]


def test_dry_run_makes_no_network_calls(tmp_path, monkeypatch, capsys):
    (tmp_path / "conversations.json").write_text(json.dumps([_conv("a"), _conv("b")]))

    def _boom(*a, **k):
        raise AssertionError("network call in dry run")

    monkeypatch.setattr(ingest.requests, "post", _boom)
    ingest.main([str(tmp_path), "--dry-run"])
    out = capsys.readouterr().out
    assert "2 conversations" in out
    assert "2 items" in out
```

- [ ] **Step 2: Run the test and confirm it fails**

`cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_ingest_chatgpt_facts_script.py`
Expected: FAIL during collection with `FileNotFoundError: [Errno 2] No such file or directory: '.../scripts/ingest_chatgpt_facts.py'`.

- [ ] **Step 3: Implement**

`scripts/ingest_chatgpt_facts.py`:
```python
#!/usr/bin/env python3
"""
Extract fact candidates from a ChatGPT export and send them to UpApply's /facts/ingest.

Only the freelancer's own (user) turns are SOURCE TEXT. The last assistant message
(usually the final letter) travels as CONTEXT so the extractor can interpret what the
user was correcting — assistant text is never stored as voice and never a fact source.

Usage:
    UPAPPLY_PASSWORD='...' python scripts/ingest_chatgpt_facts.py \\
        /Users/admin/dev2/UpApply/working/chatgpt-export \\
        --email chris@servicevision.net \\
        [--api https://upapply-api.onrender.com] [--batch-size 5] [--limit N] [--dry-run]

Re-runnable: conversations already ingested (by conversation id) are skipped server-side.
Candidates land in the Facts review page (status=candidate) unless they match an
already-approved fact at >= 0.92 similarity, in which case they merge and stay approved.
"""
import argparse
import getpass
import json
import os
import sys
from pathlib import Path

import requests

DEFAULT_EXPORT_DIR = "/Users/admin/dev2/UpApply/working/chatgpt-export"
API_BASE = "https://upapply-api.onrender.com"
SOURCE_TYPE = "chatgpt_user_turn"
MAX_SOURCE_CHARS = 12000
MAX_CONTEXT_CHARS = 4000
MIN_USER_CHARS = 40


def load_conversations(export_dir: Path) -> list[dict]:
    """Read conversations-*.json (new export layout) or conversations.json (old layout)."""
    files = sorted(export_dir.glob("conversations-*.json")) or sorted(export_dir.glob("conversations.json"))
    conversations: list[dict] = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, list):
            conversations.extend(data)
    return conversations


def conversation_messages(conv: dict) -> list[tuple[str, str]]:
    """Ordered (role, text) pairs along the active branch (current_node back to root)."""
    mapping = conv.get("mapping") or {}
    chain: list[str] = []
    seen: set[str] = set()
    node_id = conv.get("current_node")
    while node_id and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        chain.append(node_id)
        node_id = (mapping[node_id] or {}).get("parent")

    messages: list[tuple[str, str]] = []
    for nid in reversed(chain):
        msg = (mapping[nid] or {}).get("message") or {}
        role = (msg.get("author") or {}).get("role")
        if role not in ("user", "assistant"):
            continue
        parts = (msg.get("content") or {}).get("parts") or []
        text = "\n".join(p for p in parts if isinstance(p, str)).strip()
        if text:
            messages.append((role, text))
    return messages


def chunk_text(text: str, size: int) -> list[str]:
    """Split on paragraph boundaries into chunks of at most `size` chars."""
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        while len(para) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:size])
            para = para[size:]
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > size:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def build_items(conv: dict) -> list[dict]:
    """FactIngestItem dicts for one conversation (empty when nothing worth extracting)."""
    conv_id = conv.get("id") or conv.get("conversation_id")
    if not conv_id:
        return []
    messages = conversation_messages(conv)
    user_text = "\n\n".join(t for role, t in messages if role == "user")
    if len(user_text) < MIN_USER_CHARS:
        return []

    assistant = [t for role, t in messages if role == "assistant"]
    context = f"Conversation title: {conv.get('title') or ''}"
    if assistant:
        context += f"\n\nFinal assistant message:\n{assistant[-1][:MAX_CONTEXT_CHARS]}"

    chunks = chunk_text(user_text, MAX_SOURCE_CHARS)
    return [
        {
            "text": chunk,
            "source_ref": conv_id if len(chunks) == 1 else f"{conv_id}#{n + 1}",
            "context": context,
        }
        for n, chunk in enumerate(chunks)
    ]


def login(api: str, email: str, password: str) -> str:
    resp = requests.post(f"{api}/api/v1/auth/login", json={"email": email, "password": password}, timeout=30)
    if not resp.ok:
        print(f"Login failed: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)
    return resp.json()["access_token"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract fact candidates from a ChatGPT export")
    parser.add_argument("export_dir", nargs="?", default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--email", help="UpApply account email (required unless --dry-run)")
    parser.add_argument("--api", default=API_BASE)
    parser.add_argument("--batch-size", type=int, default=5, help="Items per /facts/ingest call (max 25)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N conversations")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report; no API calls")
    args = parser.parse_args(argv)

    export_dir = Path(args.export_dir)
    conversations = load_conversations(export_dir)
    if args.limit:
        conversations = conversations[: args.limit]
    items = [item for conv in conversations for item in build_items(conv)]
    print(f"{len(conversations)} conversations -> {len(items)} items from {export_dir}")

    if args.dry_run:
        for item in items[:3]:
            print(f"--- {item['source_ref']} ---\n{item['text'][:400]}\n")
        return

    if not args.email:
        parser.error("--email is required unless --dry-run")
    password = os.environ.get("UPAPPLY_PASSWORD") or getpass.getpass("UpApply password: ")
    api = args.api.rstrip("/")
    headers = {"Authorization": f"Bearer {login(api, args.email, password)}"}

    batch_size = max(1, min(args.batch_size, 25))
    totals = {"created": 0, "merged": 0, "auto_approved": 0, "skipped": 0, "failed": 0}
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        resp = requests.post(
            f"{api}/api/v1/facts/ingest",
            json={"source_type": SOURCE_TYPE, "items": batch, "auto_approve": False},
            headers=headers,
            timeout=600,
        )
        if not resp.ok:
            print(f"  Batch {start // batch_size + 1} failed: {resp.status_code} {resp.text[:300]}")
            totals["failed"] += len(batch)
            continue
        result = resp.json()
        for key in totals:
            totals[key] += result.get(key, 0)
        print(f"  {min(start + batch_size, len(items))}/{len(items)} items — {result}")

    print(f"Done: {totals}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test and confirm it passes**

`cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_ingest_chatgpt_facts_script.py`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add scripts/ingest_chatgpt_facts.py api/tests/test_ingest_chatgpt_facts_script.py
git commit -m "$(cat <<'EOF'
feat(knowledge): scripts/ingest_chatgpt_facts.py — user turns -> /facts/ingest (dry-run, chunked, idempotent)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.10: Extension scraper captures the full letter, answers and job description separately

**Files:**
- Modify: `extension/src/content/scrapers/proposals.ts` (replace `scrapeProposalPageText`, lines 264-299)
- Modify: `extension/src/content/index.ts` (line 15 import; the `SCRAPE_PROPOSAL_DETAIL` case, lines 712-720)
- Modify: `extension/src/types/index.ts` (`ScrapedProposal`, lines 30-40)
- Modify: `extension/src/background/index.ts` (the `IMPORT_PROPOSALS` detail loop, lines 727-814)

**Interfaces:**
- Produces: `scrapeProposalDetail(): ProposalDetail` with `{ coverLetter: string | null; answers: { question: string; answer: string }[] }`. This replaces `scrapeProposalPageText`, which used to merge the answers into the letter.
- `ScrapedProposal` gains `screeningAnswers?` and `jobDescription?`. These flow unchanged through `apiClient.importProposalsFromUpwork` into Task 1.8's endpoint.
- NUXT paths, confirmed from `working/proposaldetails.html`:
  - `state['proposal-details'].proposalDetailsV3Response.application.questionsAnswers[] {question, answer}`, which is untruncated.
  - `...proposalDetailsV3Response.jobDetails.opening.job.description`.
- The DOM answers serve only as a fallback because they are truncated.
- Status already flows through as before.

- [ ] **Step 1: Make the consumer reference the new API (red)**

In `extension/src/content/index.ts`, change line 15 to:
```ts
import { extractAllProposals, scrapeProposalDetail } from './scrapers/proposals';
```
and replace the `SCRAPE_PROPOSAL_DETAIL` case (lines 712-720) with:
```ts
    case 'SCRAPE_PROPOSAL_DETAIL': {
      // Extract cover letter, screening answers and title from a single /nx/proposals/{id} page.
      // Called by the background IMPORT_PROPOSALS deep-scraper when window.__NUXT__ is unavailable.
      const { coverLetter, answers } = scrapeProposalDetail();
      // Use a specific selector; avoid generic h3 which can match section headers like "Hiring activity"
      const titleEl = document.querySelector<HTMLElement>('[data-test="job-title"], h2.job-title, .job-title');
      const jobTitle = titleEl?.textContent?.trim() || null;
      sendResponse({ success: true, coverLetter, answers, jobTitle });
      break;
    }
```

- [ ] **Step 2: Run the type-check and confirm it fails**

`cd /Users/admin/dev2/UpApply/extension && npm run type-check`
Expected: FAIL with `src/content/index.ts(15,31): error TS2305: Module '"./scrapers/proposals"' has no exported member 'scrapeProposalDetail'.`

- [ ] **Step 3: Implement the scraper, types and background capture**

In `extension/src/content/scrapers/proposals.ts`, replace lines 264-299 (the `scrapeProposalPageText` doc comment and function) with:
```ts
export interface ProposalDetail {
  coverLetter: string | null;
  answers: { question: string; answer: string }[];
}

/**
 * Extract the submitted cover letter and screening answers from an Upwork proposal
 * detail page. DOM fallback only — the background prefers window.__NUXT__, whose
 * answers are never truncated.
 *
 * DOM structure (confirmed from proposaldetails.html):
 *   div[data-cy="cover-letter-section"]
 *     p.break.text-pre-line                       ← cover letter
 *     [data-test="questions-answers"] li
 *       strong                                    ← question
 *       span.air3-truncation span[id]             ← answer (may end in "…" + "more")
 */
export function scrapeProposalDetail(): ProposalDetail {
  let coverLetter: string | null = null;
  const answers: { question: string; answer: string }[] = [];

  const section = document.querySelector('[data-cy="cover-letter-section"]');
  if (section) {
    const parts: string[] = [];
    section.querySelectorAll('p.break.text-pre-line').forEach(p => {
      const t = p.textContent?.trim();
      if (t) parts.push(t);
    });
    const joined = parts.join('\n\n');
    if (joined.length > 50) coverLetter = joined;

    section.querySelectorAll('[data-test="questions-answers"] li').forEach(li => {
      const question = li.querySelector('strong')?.textContent?.trim() || '';
      const answer =
        li.querySelector('span.air3-truncation span[id]')?.textContent?.trim() ||
        li.querySelector('span.air3-truncation')?.textContent?.trim() ||
        '';
      if (answer) answers.push({ question, answer });
    });
  }

  if (!coverLetter) {
    // Fallback: .cover-letter-section (older Upwork markup)
    const fallback = document.querySelector('.cover-letter-section p.break, .cover-letter p');
    const t = fallback?.textContent?.trim();
    if (t && t.length > 50) coverLetter = t;
  }

  return { coverLetter, answers };
}
```

In `extension/src/types/index.ts`, inside `ScrapedProposal` after `wasHired?: boolean | null;` add:
```ts
  screeningAnswers?: { question: string; answer: string }[];
  jobDescription?: string | null;
```

In `extension/src/background/index.ts`, replace lines 727-814 (from `// Read window.__NUXT__ from the page's main world` through the closing `});` of `results.push({...})`) with:
```ts
              // Read window.__NUXT__ from the page's main world
              type QA = { question: string; answer: string };
              let nuxtCoverLetter: string | null = null;
              let nuxtStatus: string | null = null;
              let nuxtBidAmount: string | null = null;
              let nuxtJobTitle: string | null = null;
              let nuxtAnswers: QA[] = [];
              let nuxtJobDescription: string | null = null;
              try {
                const [nuxtResult] = await chrome.scripting.executeScript({
                  target: { tabId: propTab.id },
                  world: 'MAIN',
                  func: () => {
                    const empty = { coverLetter: null, status: null, bidAmount: null, jobTitle: null, answers: [], jobDescription: null };
                    try {
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const n = (window as any).__NUXT__;
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const state = n?.state as Record<string, any> | undefined;
                      // Correct path: __NUXT__.state['proposal-details'].proposalDetailsV3Response.application
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const v3 = state?.['proposal-details']?.proposalDetailsV3Response as Record<string, any> | undefined;
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const app = v3?.application as Record<string, any> | undefined;
                      // status may be a number (Upwork internal enum) — convert to string
                      const rawStatus = app?.status;
                      const statusStr = rawStatus != null ? String(rawStatus) : null;
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const qa = Array.isArray(app?.questionsAnswers) ? (app!.questionsAnswers as any[]) : [];
                      return {
                        coverLetter: (app?.coverLetter as string) || null,
                        status: statusStr,
                        bidAmount: String(app?.terms?.chargeRate?.amount || '') || null,
                        jobTitle: (v3?.jobDetails?.opening?.job?.info?.title as string) || null,
                        answers: qa
                          .map(x => ({ question: String(x?.question ?? ''), answer: String(x?.answer ?? '') }))
                          .filter(x => x.answer.trim().length > 0),
                        jobDescription: (v3?.jobDetails?.opening?.job?.description as string) || null,
                      };
                    } catch { return empty; }
                  },
                });
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const r = nuxtResult?.result as Record<string, any> | null;
                nuxtCoverLetter = r?.coverLetter || null;
                nuxtStatus = r?.status || null;
                nuxtBidAmount = r?.bidAmount || null;
                nuxtJobTitle = r?.jobTitle || null;
                nuxtAnswers = (r?.answers as QA[]) || [];
                nuxtJobDescription = r?.jobDescription || null;
              } catch (e) {
                logger.log('UpApply: NUXT read failed for proposal', proposal.proposalId, String(e));
              }

              // DOM fallback via content script (already injected by manifest — no re-inject)
              let domCoverLetter: string | null = null;
              let domAnswers: QA[] = [];
              if (!nuxtCoverLetter || nuxtAnswers.length === 0) {
                await waitForContentScript(propTab.id, 5_000);
                const domResult = await new Promise<{ coverLetter?: string | null; answers?: QA[] }>((resolve) => {
                  chrome.tabs.sendMessage(propTab.id!, { type: 'SCRAPE_PROPOSAL_DETAIL' }, (resp) => {
                    if (chrome.runtime.lastError || !resp?.success) resolve({});
                    else resolve(resp);
                  });
                });
                domCoverLetter = domResult.coverLetter || null;
                domAnswers = domResult.answers || [];
              }

              const coverLetter = nuxtCoverLetter || domCoverLetter || null;
              // domJobTitle is unreliable (generic h3 may say "Hiring activity"); prefer list-page title
              const jobTitle = nuxtJobTitle || proposal.jobTitle;

              // Determine was_hired from multiple signals:
              // 1. List-page status text (most reliable for won state)
              // 2. Nuxt detail-page status (may be numeric enum or string)
              let wasHired: boolean | null = null;
              const listStatus = (proposal.status || '').toLowerCase();
              const detailStatus = (nuxtStatus || '').toLowerCase();
              const hiredKeywords = ['hired', 'contract', 'working', 'active contract'];
              const isHiredByList = hiredKeywords.some(k => listStatus.includes(k));
              const isHiredByDetail = hiredKeywords.some(k => detailStatus.includes(k));
              if (isHiredByList || isHiredByDetail) {
                wasHired = true;
              } else if (proposal._isArchived) {
                wasHired = false;
              }

              results.push({
                proposalId: proposal.proposalId,
                jobTitle,
                jobUrl: detailUrl,
                coverLetter,
                bidAmount: nuxtBidAmount ? parseFloat(nuxtBidAmount) : null,
                bidType: null,
                status: nuxtStatus || (proposal._isArchived ? 'archived' : (proposal.status || 'submitted')),
                submittedAt: proposal.submittedAt,
                wasHired,
                screeningAnswers: nuxtAnswers.length ? nuxtAnswers : domAnswers,
                jobDescription: nuxtJobDescription,
              });
```

- [ ] **Step 4: Run the type-check and confirm it passes**

`cd /Users/admin/dev2/UpApply/extension && npm run type-check`
Expected: exits 0 with no errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add extension/src/content/scrapers/proposals.ts extension/src/content/index.ts \
  extension/src/types/index.ts extension/src/background/index.ts
git commit -m "$(cat <<'EOF'
feat(extension): proposal detail scrape captures screening answers + job description separately

Reads untruncated questionsAnswers and job description from __NUXT__; DOM fallback
no longer merges answers into the cover letter.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.11: Facts review page in the sidebar and API client methods

**Files:**
- Create: `extension/src/sidebar/pages/FactsPage.tsx`
- Modify: `extension/src/sidebar/pages/MePage.tsx` (lines 1-43: add the `facts` tab)
- Modify: `extension/src/lib/api-client.ts` (methods inserted before the class's closing `}` at line 677; types appended at the end of the file)

**Interfaces:**
- Consumes: `GET/PATCH /facts`, `POST /facts/bulk-approve`, `POST /facts/from-memories` and `POST /facts/from-proposals` (Tasks 1.5 and 1.6).
- Produces these `apiClient` methods:
  - `getFacts(status?: FactStatus): Promise<Fact[]>`
  - `updateFact(id: string, patch: FactUpdate): Promise<Fact>`
  - `bulkApproveFacts(ids: string[]): Promise<{ approved: number }>`
  - `factsFromMemories(): Promise<FactIngestResult>`
  - `factsFromProposals(limit?: number): Promise<FactIngestResult>`
- It also exports the types `Fact`, `FactKind`, `FactStatus`, `FactSource`, `FactUpdate` and `FactIngestResult`.
- The page is `sidebar/pages/FactsPage.tsx`, reached through **Me → Facts**.

- [ ] **Step 1: Write the page and wire the tab (red, since the client methods don't exist yet)**

`extension/src/sidebar/pages/FactsPage.tsx`:
```tsx
import { useEffect, useMemo, useState } from 'react';
import { apiClient, Fact, FactKind, FactStatus } from '../../lib/api-client';

const KIND_LABELS: Record<FactKind, string> = {
  metric: 'Metrics',
  outcome: 'Outcomes',
  project: 'Projects',
  client_quote: 'Client quotes',
  credential: 'Credentials',
  role: 'Roles',
  tech: 'Tech',
};
const KIND_ORDER: FactKind[] = ['metric', 'outcome', 'project', 'client_quote', 'credential', 'role', 'tech'];
const STATUS_TABS: FactStatus[] = ['candidate', 'approved', 'rejected'];
const STATUS_LABELS: Record<FactStatus, string> = { candidate: 'To review', approved: 'Approved', rejected: 'Rejected' };

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export default function FactsPage() {
  const [status, setStatus] = useState<FactStatus>('candidate');
  const [facts, setFacts] = useState<Fact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async (s: FactStatus) => {
    setLoading(true);
    setError(null);
    setSelected(new Set());
    try {
      setFacts(await apiClient.getFacts(s));
    } catch (err) {
      setError(errorText(err, 'Failed to load facts.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(status);
  }, [status]);

  const groups = useMemo(
    () => KIND_ORDER
      .map(kind => ({ kind, items: facts.filter(f => f.kind === kind) }))
      .filter(g => g.items.length > 0),
    [facts],
  );

  const setFactStatus = async (fact: Fact, next: FactStatus) => {
    try {
      await apiClient.updateFact(fact.id, { status: next });
      setFacts(prev => prev.filter(f => f.id !== fact.id));
    } catch (err) {
      setError(errorText(err, 'Update failed.'));
    }
  };

  const saveEdit = async (fact: Fact) => {
    const statement = draft.trim();
    if (!statement) return;
    try {
      const updated = await apiClient.updateFact(fact.id, { statement });
      setFacts(prev => prev.map(f => (f.id === fact.id ? updated : f)));
      setEditingId(null);
    } catch (err) {
      setError(errorText(err, 'Save failed.'));
    }
  };

  const toggle = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleGroup = (items: Fact[]) => {
    setSelected(prev => {
      const next = new Set(prev);
      const allSelected = items.every(f => next.has(f.id));
      items.forEach(f => (allSelected ? next.delete(f.id) : next.add(f.id)));
      return next;
    });
  };

  const bulkApprove = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    try {
      const result = await apiClient.bulkApproveFacts(ids);
      setFacts(prev => prev.filter(f => !selected.has(f.id)));
      setSelected(new Set());
      setNotice(`Approved ${result.approved} facts.`);
    } catch (err) {
      setError(errorText(err, 'Bulk approve failed.'));
    }
  };

  const runExtraction = async (from: 'memories' | 'proposals') => {
    setBusy(true);
    setError(null);
    setNotice(from === 'memories' ? 'Extracting facts from bio memories…' : 'Extracting facts from Upwork proposals…');
    try {
      const r = from === 'memories' ? await apiClient.factsFromMemories() : await apiClient.factsFromProposals(10);
      setNotice(
        `${r.created} new · ${r.merged} merged · ${r.auto_approved} auto-approved · ${r.skipped} already done` +
        (r.failed ? ` · ${r.failed} failed` : '') +
        (r.remaining ? ` · ${r.remaining} proposals left, run again` : ''),
      );
      await load(status);
    } catch (err) {
      setError(errorText(err, 'Extraction failed.'));
      setNotice(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-4 space-y-3">
      <div className="flex gap-1">
        {STATUS_TABS.map(s => (
          <button
            key={s}
            type="button"
            onClick={() => setStatus(s)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
              status === s ? 'bg-emerald-100 text-emerald-700' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
            }`}
          >
            {STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => runExtraction('memories')}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:border-emerald-300 disabled:opacity-50"
        >
          From bio memories
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => runExtraction('proposals')}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:border-emerald-300 disabled:opacity-50"
        >
          From Upwork proposals
        </button>
        {status === 'candidate' && selected.size > 0 && (
          <button
            type="button"
            onClick={bulkApprove}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700"
          >
            Approve {selected.size} selected
          </button>
        )}
      </div>

      {notice && <p className="text-xs text-gray-600 bg-gray-100 rounded-lg px-3 py-2">{notice}</p>}
      {error && <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
      {loading && <p className="text-xs text-gray-400">Loading facts…</p>}
      {!loading && facts.length === 0 && (
        <p className="text-xs text-gray-400">No {STATUS_LABELS[status].toLowerCase()} facts.</p>
      )}

      {groups.map(({ kind, items }) => (
        <section key={kind} className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">
              {KIND_LABELS[kind]} ({items.length})
            </h3>
            {status === 'candidate' && (
              <button type="button" onClick={() => toggleGroup(items)} className="text-[11px] text-emerald-700 hover:underline">
                {items.every(f => selected.has(f.id)) ? 'Clear' : 'Select all'}
              </button>
            )}
          </div>

          {items.map(fact => {
            const source = fact.sources[0];
            return (
              <div key={fact.id} className="bg-white border border-gray-100 rounded-xl p-3 space-y-2">
                <div className="flex items-start gap-2">
                  {status === 'candidate' && (
                    <input
                      type="checkbox"
                      checked={selected.has(fact.id)}
                      onChange={() => toggle(fact.id)}
                      className="mt-1 accent-emerald-600"
                    />
                  )}
                  {editingId === fact.id ? (
                    <textarea
                      value={draft}
                      onChange={e => setDraft(e.target.value)}
                      rows={3}
                      className="flex-1 text-sm border border-gray-200 rounded-lg p-2"
                    />
                  ) : (
                    <p className="flex-1 text-sm text-gray-800">{fact.statement}</p>
                  )}
                  <span className="text-[10px] text-gray-400 tabular-nums">{fact.strength.toFixed(1)}</span>
                </div>

                {source?.snippet && (
                  <p className="text-[11px] text-gray-500 italic border-l-2 border-gray-200 pl-2">
                    “{source.snippet}”
                  </p>
                )}
                <p className="text-[10px] text-gray-400">
                  {source?.source_type ?? fact.source_type}
                  {fact.sources.length > 1 ? ` · ${fact.sources.length} sources` : ''}
                  {fact.job_types.length ? ` · ${fact.job_types.join(', ')}` : ''}
                </p>

                <div className="flex gap-2">
                  {editingId === fact.id ? (
                    <>
                      <button type="button" onClick={() => saveEdit(fact)} className="text-xs text-emerald-700 font-medium">Save</button>
                      <button type="button" onClick={() => setEditingId(null)} className="text-xs text-gray-500">Cancel</button>
                    </>
                  ) : (
                    <>
                      {status !== 'approved' && (
                        <button type="button" onClick={() => setFactStatus(fact, 'approved')} className="text-xs text-emerald-700 font-medium">
                          Approve
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => { setEditingId(fact.id); setDraft(fact.statement); }}
                        className="text-xs text-gray-600"
                      >
                        Edit
                      </button>
                      {status !== 'rejected' && (
                        <button type="button" onClick={() => setFactStatus(fact, 'rejected')} className="text-xs text-red-600">
                          Reject
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}
```

Replace `extension/src/sidebar/pages/MePage.tsx` (all 43 lines) with:
```tsx
import { useState } from 'react';
import MemoriesPage from './Memories';
import SkillsPage from './Skills';
import EditProfilePage from './EditProfile';
import OptimizePage from './OptimizePage';
import FactsPage from './FactsPage';

type MeTab = 'profile' | 'skills' | 'memories' | 'facts' | 'optimize';

export default function MePage() {
  const [activeTab, setActiveTab] = useState<MeTab>('profile');

  return (
    <div className="flex flex-col h-full">
      {/* Sub-nav */}
      <div className="bg-white border-b px-4 pt-3 flex-shrink-0">
        <div className="flex gap-1 pb-2">
          {(['profile', 'skills', 'memories', 'facts', 'optimize'] as MeTab[]).map(tab => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                activeTab === tab
                  ? 'bg-emerald-100 text-emerald-700'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Content — hide the sub-page's own back-button header */}
      <div className="flex-1 overflow-auto [&>div>header]:hidden">
        {activeTab === 'profile' && <EditProfilePage />}
        {activeTab === 'skills' && <SkillsPage />}
        {activeTab === 'memories' && <MemoriesPage />}
        {activeTab === 'facts' && <FactsPage />}
        {activeTab === 'optimize' && <OptimizePage />}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run the type-check and confirm it fails**

`cd /Users/admin/dev2/UpApply/extension && npm run type-check`
Expected: FAIL with errors such as `src/sidebar/pages/FactsPage.tsx(2,23): error TS2305: Module '"../../lib/api-client"' has no exported member 'Fact'.` and `Property 'getFacts' does not exist on type 'ApiClient'.`

- [ ] **Step 3: Implement the client methods and types**

In `extension/src/lib/api-client.ts`, insert before the class's closing `}` (line 677, right after `getAgentRoi()`):
```ts

  // ── Facts (knowledge layer) ─────────────────────────────────────────────────

  async getFacts(status?: FactStatus): Promise<Fact[]> {
    const qs = status ? `?status=${status}` : '';
    return this.request<Fact[]>(`/api/v1/facts${qs}`);
  }

  async updateFact(id: string, patch: FactUpdate): Promise<Fact> {
    return this.request<Fact>(`/api/v1/facts/${id}`, { method: 'PATCH', body: patch });
  }

  async bulkApproveFacts(ids: string[]): Promise<{ approved: number }> {
    return this.request<{ approved: number }>('/api/v1/facts/bulk-approve', {
      method: 'POST',
      body: { ids },
    });
  }

  async factsFromMemories(): Promise<FactIngestResult> {
    return this.request<FactIngestResult>('/api/v1/facts/from-memories', { method: 'POST' });
  }

  async factsFromProposals(limit = 10): Promise<FactIngestResult> {
    return this.request<FactIngestResult>(`/api/v1/facts/from-proposals?limit=${limit}`, { method: 'POST' });
  }
```
Append at the end of the file:
```ts

// ── Facts (knowledge layer) ───────────────────────────────────────────────────

export type FactKind = 'project' | 'metric' | 'credential' | 'client_quote' | 'role' | 'tech' | 'outcome';
export type FactStatus = 'candidate' | 'approved' | 'rejected';

export interface FactSource {
  source_type: string;
  source_ref: string | null;
  snippet: string | null;
}

export interface Fact {
  id: string;
  kind: FactKind;
  statement: string;
  detail: string | null;
  skills: string[];
  industries: string[];
  job_types: string[];
  strength: number;
  status: FactStatus;
  source_type: string;
  source_ref: string | null;
  sources: FactSource[];
  times_used: number;
  times_in_won: number;
  created_at: string;
  updated_at: string;
}

export interface FactUpdate {
  statement?: string;
  detail?: string | null;
  status?: FactStatus;
  kind?: FactKind;
  skills?: string[];
  job_types?: string[];
  strength?: number;
}

export interface FactIngestResult {
  created: number;
  merged: number;
  auto_approved: number;
  skipped: number;
  failed: number;
  remaining: number;
}
```

- [ ] **Step 4: Run the type-check and confirm it passes**

`cd /Users/admin/dev2/UpApply/extension && npm run type-check`
Expected: exits 0.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add extension/src/sidebar/pages/FactsPage.tsx extension/src/sidebar/pages/MePage.tsx extension/src/lib/api-client.ts
git commit -m "$(cat <<'EOF'
feat(extension): Facts review tab (Me -> Facts) — grouped candidates, approve/edit/reject, bulk-approve

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.12: Contract and client-feedback facts (spec §1.3.3)

Spec §1.3.3 turns contracts and client feedback into `client_quote` and `outcome` facts. The contract data UpApply already holds is the contract list that `POST /jobs/import-contracts` stores as `jobs` rows: `source='contract_import'`, `upwork_job_id='contract_<id>'`, and a description made of the title, rate, client and dates. Client feedback text is not on any page we have a fixture for (`working/contractdetails.html` shows only the "feedback not provided" block), so feedback comes in by paste on the Facts page. Both paths go through the existing `ingest_items` pipeline, so dedupe, the §1.7 auto-approve rule and idempotency behave as for every other source.

**Files:**
- Modify: `api/app/services/fact_extraction.py` (add `SOURCE_LABELS`; one paragraph in `EXTRACTION_SYSTEM`; the `user =` line in `extract_facts`)
- Modify: `api/app/api/v1/facts.py` (import `Job` and `_already_ingested`; append the `/from-contracts` route)
- Modify: `api/tests/test_fact_extraction.py` (append one test)
- Modify: `api/tests/test_facts_ingest_api.py` (append one test)
- Modify: `extension/src/lib/api-client.ts` (two methods after `factsFromProposals`)
- Modify: `extension/src/sidebar/pages/FactsPage.tsx` (a "From Upwork contracts" button and a client-feedback paste box)

**Interfaces:**
- Consumes: `ingest_items` and `_already_ingested` (Task 1.6), `extract_facts` (Task 1.3), and the `Job` rows written by the existing `POST /api/v1/jobs/import-contracts`.
- Produces:
  - `POST /api/v1/facts/from-contracts` returns `FactIngestResult`. It ingests every `contract_import` job not yet listed in any fact's sources, with `source_type='upwork_contract'` and `source_ref=jobs.upwork_job_id`, as candidates that are never auto-approved. It processes at most 100 per call.
  - Client feedback uses the existing `POST /api/v1/facts/ingest` with `source_type='client_feedback'`.
  - `SOURCE_LABELS: dict[str, str]` and `DEFAULT_SOURCE_LABEL` in `fact_extraction.py`. `client_feedback` and `upwork_contract` sources are labelled as records about the freelancer instead of "written by the freelancer".
  - `apiClient.factsFromContracts(): Promise<FactIngestResult>`; `apiClient.ingestFacts(sourceType: string, items: { text: string; source_ref?: string; context?: string }[]): Promise<FactIngestResult>`.

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_fact_extraction.py`:
```python


@pytest.mark.asyncio
async def test_client_feedback_is_labelled_as_a_record_not_the_freelancers_words():
    mock = AsyncMock(return_value={"facts": []})
    with patch("app.services.fact_extraction.structured_call", mock):
        await extract_facts("Chris saved our launch. Would hire again.", source_type="client_feedback")
    user = mock.call_args.kwargs["user"]
    assert "client feedback about the freelancer" in user
    assert "written by the freelancer" not in user
```

Append to `api/tests/test_facts_ingest_api.py`:
```python


@pytest.mark.asyncio
async def test_from_contracts_ingests_contract_jobs_once_as_candidates(client: AsyncClient, auth_headers: dict, fake_embed):
    from app.models.job import Job

    uid = await _user_id(client, auth_headers)
    async with TestSessionLocal() as s:
        s.add_all([
            Job(user_id=uid, upwork_job_id="contract_1", upwork_url="https://www.upwork.com/nx/wm/workroom/1/overview",
                title="SQL Server tuning", description="SQL Server tuning\nRate: $95/hr\nClient: Acme Health",
                source="contract_import", is_saved=True),
            Job(user_id=uid, upwork_job_id="~01abc", upwork_url="https://www.upwork.com/jobs/~01abc",
                title="Not a contract", description="A job post", source="extension"),
        ])
        await s.commit()

    extract = AsyncMock(side_effect=_per_ref_extract)
    with patch("app.services.facts.extract_facts", extract):
        r = await client.post(f"{BASE}/from-contracts", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["created"] == 1
        r = await client.post(f"{BASE}/from-contracts", headers=auth_headers)
        assert r.json()["created"] == 0
    assert [(c.args[1], c.args[2]) for c in extract.await_args_list] == [("upwork_contract", "contract_1")]
    assert "Acme Health" in extract.await_args_list[0].args[0]
    candidates = (await client.get(BASE, headers=auth_headers, params={"status": "candidate"})).json()
    assert [f["source_type"] for f in candidates] == ["upwork_contract"]
```

- [ ] **Step 2: Run the tests and confirm they fail**

`cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_fact_extraction.py tests/test_facts_ingest_api.py`
Expected: 2 failed. The extraction test fails on `assert "client feedback about the freelancer" in user`, and the contracts test gets a 404 from `/facts/from-contracts`.

- [ ] **Step 3: Implement**

In `api/app/services/fact_extraction.py`, after the `JOB_TYPES = [...]` line, add:
```python
# Sources that are records ABOUT the freelancer rather than text they wrote (spec §1.3.3)
SOURCE_LABELS = {
    "client_feedback": "SOURCE TEXT (client feedback about the freelancer, copied from Upwork)",
    "upwork_contract": "SOURCE TEXT (Upwork contract record for the freelancer's own work)",
}
DEFAULT_SOURCE_LABEL = "SOURCE TEXT (written by the freelancer)"
```
In `EXTRACTION_SYSTEM`, directly before the line `What to skip: the requirements of a client's job post, generic advice, opinions,`, insert this paragraph followed by one blank line:
```
Some SOURCE TEXT is a client's feedback or an Upwork contract record about the
freelancer rather than their own words; it is still SOURCE TEXT. Client feedback
becomes `client_quote` facts whose statement quotes the client's words exactly.
```
In `extract_facts`, replace:
```python
    user = f"SOURCE TEXT (written by the freelancer):\n<<<\n{text}\n>>>"
```
with:
```python
    label = SOURCE_LABELS.get(source_type, DEFAULT_SOURCE_LABEL)
    user = f"{label}:\n<<<\n{text}\n>>>"
```

In `api/app/api/v1/facts.py`, add `from app.models.job import Job` after `from app.models.fact import Fact`, and change `from app.services.facts import fact_embedding_text, ingest_items, upsert_candidate_outcome` to:
```python
from app.services.facts import _already_ingested, fact_embedding_text, ingest_items, upsert_candidate_outcome
```
Append:
```python
@router.post("/from-contracts", response_model=FactIngestResult)
async def facts_from_contracts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fact candidates from imported Upwork contracts (spec §1.3.3). Never auto-approved."""
    jobs = (await db.execute(
        select(Job)
        .where(
            Job.user_id == current_user.id,
            Job.source == "contract_import",
            Job.upwork_job_id.is_not(None),
        )
        .order_by(Job.created_at.desc())
    )).scalars().all()
    pending = [
        j for j in jobs
        if not await _already_ingested(db, current_user.id, "upwork_contract", j.upwork_job_id)
    ][:100]
    items = [FactIngestItem(text=j.description or j.title, source_ref=j.upwork_job_id) for j in pending]
    counts = await ingest_items(db, current_user.id, "upwork_contract", items)
    await db.commit()
    return FactIngestResult(**counts)
```
A contract record that yields zero facts is retried on the next click. Contract records are short and few, so the repeat Haiku cost is negligible.

In `extension/src/lib/api-client.ts`, after `factsFromProposals`, add:
```ts

  async factsFromContracts(): Promise<FactIngestResult> {
    return this.request<FactIngestResult>('/api/v1/facts/from-contracts', { method: 'POST' });
  }

  async ingestFacts(
    sourceType: string,
    items: { text: string; source_ref?: string; context?: string }[],
  ): Promise<FactIngestResult> {
    return this.request<FactIngestResult>('/api/v1/facts/ingest', {
      method: 'POST',
      body: { source_type: sourceType, items },
    });
  }
```

In `extension/src/sidebar/pages/FactsPage.tsx`:

1. Next to the existing `useState` hooks, add:
```tsx
  const [feedbackText, setFeedbackText] = useState('');
  const [feedbackContract, setFeedbackContract] = useState('');
```
2. Replace the whole `runExtraction` function (Task 1.11) with:
```tsx
  const runExtraction = async (from: 'memories' | 'proposals' | 'contracts') => {
    setBusy(true);
    setError(null);
    setNotice(
      from === 'memories' ? 'Extracting facts from bio memories…'
        : from === 'proposals' ? 'Extracting facts from Upwork proposals…'
        : 'Extracting facts from Upwork contracts…',
    );
    try {
      const r = from === 'memories' ? await apiClient.factsFromMemories()
        : from === 'proposals' ? await apiClient.factsFromProposals(10)
        : await apiClient.factsFromContracts();
      setNotice(
        `${r.created} new · ${r.merged} merged · ${r.auto_approved} auto-approved · ${r.skipped} already done` +
        (r.failed ? ` · ${r.failed} failed` : '') +
        (r.remaining ? ` · ${r.remaining} proposals left, run again` : ''),
      );
      await load(status);
    } catch (err) {
      setError(errorText(err, 'Extraction failed.'));
      setNotice(null);
    } finally {
      setBusy(false);
    }
  };

  const submitFeedback = async () => {
    const text = feedbackText.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      const r = await apiClient.ingestFacts('client_feedback', [
        { text, context: feedbackContract.trim() ? `Contract: ${feedbackContract.trim()}` : undefined },
      ]);
      setNotice(`${r.created} new · ${r.merged} merged · ${r.auto_approved} auto-approved from client feedback`);
      setFeedbackText('');
      setFeedbackContract('');
      await load(status);
    } catch (err) {
      setError(errorText(err, 'Could not extract facts from that feedback.'));
    } finally {
      setBusy(false);
    }
  };
```
3. After the "From Upwork proposals" `<button>` element, add:
```tsx
        <button
          type="button"
          disabled={busy}
          onClick={() => runExtraction('contracts')}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:border-emerald-300 disabled:opacity-50"
        >
          From Upwork contracts
        </button>
```
4. Directly after the closing `</div>` of that `flex flex-wrap gap-2` button row, add:
```tsx

      <details className="bg-white border border-gray-100 rounded-xl p-3">
        <summary className="text-xs font-medium text-gray-700 cursor-pointer">Add client feedback</summary>
        <div className="mt-2 space-y-2">
          <input
            type="text"
            value={feedbackContract}
            onChange={e => setFeedbackContract(e.target.value)}
            placeholder="Contract title (optional)"
            className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5"
          />
          <textarea
            value={feedbackText}
            onChange={e => setFeedbackText(e.target.value)}
            rows={4}
            placeholder="Paste the client's feedback from Upwork"
            className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5"
          />
          <button
            type="button"
            disabled={busy || !feedbackText.trim()}
            onClick={submitFeedback}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Extract facts
          </button>
        </div>
      </details>
```

- [ ] **Step 4: Run the tests and the type-check, and confirm they pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_fact_extraction.py tests/test_facts_ingest_api.py
cd /Users/admin/dev2/UpApply/extension && npm run type-check
```
Expected: all passed, 0 failed (5 in `test_fact_extraction.py`); `tsc --noEmit` exits 0.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/services/fact_extraction.py api/app/api/v1/facts.py api/tests/test_fact_extraction.py \
  api/tests/test_facts_ingest_api.py extension/src/lib/api-client.ts extension/src/sidebar/pages/FactsPage.tsx
git commit -m "$(cat <<'EOF'
feat(knowledge): contract and client-feedback facts (/facts/from-contracts + paste box)

Imported contract records become fact candidates (upwork_contract); pasted
client feedback goes through /facts/ingest as client_feedback, labelled as a
record about the freelancer so client praise becomes client_quote facts.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Phase 1 exit criteria

```bash
# API: full suite green (Phase 0 baseline + this phase's 48 new tests)
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q

# API imports cleanly
cd /Users/admin/dev2/UpApply/api && ./venv/bin/python -c "from app.main import app; print('OK')"

# Migration upgrade -> downgrade -> upgrade clean (Task 1.1 Step 5 script, scratch DB)

# Extension types
cd /Users/admin/dev2/UpApply/extension && npm run type-check

# Ingestion script parses a real export without network
cd /Users/admin/dev2/UpApply && api/venv/bin/python scripts/ingest_chatgpt_facts.py /Users/admin/dev2/UpApply/working/chatgpt-export --dry-run
```

---

## Phase 2: Generation engine

This phase replaces the single-prompt cover letter path with the four-step v2 pipeline from spec §2: job brief, evidence retrieval, joint write, and verify with at most one repair pass. The brief step runs on `claude-haiku-4-5` with structured output. Evidence retrieval reranks approved facts per need, adds an always-include credential floor, and picks 2-3 real voice samples. The writer is one `claude-opus-5-5` call at effort `high` that returns letter, screening answers and fact ids together, with the stable system prompt cached. Verify runs deterministic rules plus a Haiku claim audit. The pipeline sits behind the per-user `user_profiles.generation_v2` flag (migration 023), and `POST /jobs/cover-letters/generate` and `POST /screening-answers/generate` only route to it when the flag is on. With the flag off the legacy path is byte-for-byte the same model and prompt, pinned to `legacy_cover_letter_model`. Responses keep every existing field and add optional `screening_answers`, `verify_warnings` and `facts_used`. The extension shows warnings and facts under the draft, and `scripts/eval_generation.py` produces the blind A/B golden-set packet from spec §4.2.

**Branch:** `feat/mdg-2-engine`, stacked on `feat/mdg-1-knowledge`:

```bash
cd /Users/admin/dev2/UpApply && git checkout feat/mdg-1-knowledge && git pull --ff-only && git checkout -b feat/mdg-2-engine
```

**Depends on Phase 1 (consumed, not created here):** `app/models/fact.py::Fact`, `app/services/facts.py::search_facts`, the `proposals` columns `author`, `outcome` and `job_needs_embedding`, migration `022_knowledge_layer`, and `facts` in the conftest `TRUNCATE` list.

**Test command used throughout:**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q <target>
```

---

### Task 2.1: Model config, legacy pin, and usage logging in `services/llm.py`

Changing `cover_letter_model` to `claude-opus-5-5` would break the legacy path, because Opus 5.5 rejects `temperature` and the legacy calls pass it (`cover_letter.py:424,465,535`, `profile_optimizer.py:186`, `import_chatgpt.py:120`). Every legacy caller therefore moves to a new `legacy_cover_letter_model` (default `claude-sonnet-4-6`, today's value). The old path keeps its exact model and prompt, and `cover_letter_model` becomes the v2 writer model.

`app/services/llm.py` (`get_anthropic_client`, `structured_call`, `LLMError`), `tests/test_llm.py` and `settings.extraction_model` already exist from Phase 1 Task 1.2. This task only adds the two new settings, pins legacy callers, appends two tests, and adds token-usage logging to `structured_call` (needed to watch cache hits on the writer's cached system prompt).

**Files:**
- Modify: `api/app/services/llm.py` (Phase 1 Task 1.2: add usage logging after the `messages.create` call)
- Modify: `api/tests/test_llm.py` (Phase 1 Task 1.2: append two tests)
- Modify: `api/app/core/config.py` AI block (`cover_letter_model` line plus Phase 1's `extraction_model` line)
- Modify: `api/app/services/cover_letter.py:420,461,531` (`model=model or settings.cover_letter_model`)
- Modify: `api/app/services/profile_optimizer.py:178`
- Modify: `api/app/api/v1/import_chatgpt.py:116`
- Modify: `api/app/api/v1/jobs.py`: the three `model_used=settings.cover_letter_model,` lines (generate ~859, regenerate ~979, improve ~1153; Phase 0 Task 0.3 set the first two)
- Modify: `api/tests/test_cover_letter_model_used.py` (Phase 0 test: assert the legacy model)
- Modify: `api/tests/test_cover_letter.py` (append one test)

**Interfaces:**
- Consumes: `app.services.llm.structured_call`, `get_anthropic_client`, `LLMError` (Phase 1 Task 1.2, unchanged signature: `async structured_call(model: str, system: str | list, user: str, schema: dict, effort: str | None = None, max_tokens: int = 16000) -> dict`).
- Produces: `settings.cover_letter_model = "claude-opus-5-5"`, `settings.writer_effort = "high"`, `settings.legacy_cover_letter_model = "claude-sonnet-4-6"` (`settings.extraction_model = "claude-haiku-4-5"` is kept from Phase 1).

- [ ] **Step 1: Write the failing tests.** Append to `/Users/admin/dev2/UpApply/api/tests/test_llm.py` (Phase 1 created it; its imports already include `SimpleNamespace`, `AsyncMock`, `MagicMock`, `patch`, `pytest`, `structured_call` and `SCHEMA`):

```python


def test_model_defaults():
    from app.core.config import Settings

    fields = Settings.model_fields
    assert fields["cover_letter_model"].default == "claude-opus-5-5"
    assert fields["extraction_model"].default == "claude-haiku-4-5"
    assert fields["writer_effort"].default == "high"
    assert fields["legacy_cover_letter_model"].default == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_structured_call_passes_cached_system_blocks_through():
    blocks = [{"type": "text", "text": "rules", "cache_control": {"type": "ephemeral"}}]
    client = _fake_client()
    client.messages.create.return_value.usage = SimpleNamespace(
        input_tokens=10, output_tokens=5, cache_read_input_tokens=8, cache_creation_input_tokens=0
    )
    with patch("app.services.llm.get_anthropic_client", return_value=client):
        assert await structured_call("claude-opus-5-5", blocks, "u", SCHEMA) == {"a": 1}
    assert client.messages.create.call_args.kwargs["system"] == blocks
```

Append to `/Users/admin/dev2/UpApply/api/tests/test_cover_letter.py`:

```python


@pytest.mark.asyncio
async def test_legacy_generate_is_pinned_to_legacy_model():
    """Flag-off path must keep its model (Opus 5.5 rejects the legacy temperature param)."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.core.config import settings
    from app.services.cover_letter import generate_cover_letter

    profile = SimpleNamespace(
        full_name=None, professional_title=None, bio=None, career_goals=None,
        communication_style=None, unique_strengths=None, proposal_anchors=None,
        skills_to_highlight=None, preferred_closing=None,
    )
    message = MagicMock()
    message.content = [MagicMock(text="Body text.")]
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=message)
    with patch("app.services.cover_letter._get_anthropic_client", return_value=client):
        await generate_cover_letter(
            job_title="T", job_description="D", job_skills=[], budget=None,
            skill_matches=[], missing_skills=[], relevant_memories=[], profile=profile,
        )
    assert client.messages.create.call_args.kwargs["model"] == settings.legacy_cover_letter_model
```

In `/Users/admin/dev2/UpApply/api/tests/test_cover_letter_model_used.py` (from Phase 0), replace every `settings.cover_letter_model` with `settings.legacy_cover_letter_model`. That covers the guard assert and both response asserts, three occurrences:

```bash
cd /Users/admin/dev2/UpApply/api && sed -i '' 's/settings\.cover_letter_model/settings.legacy_cover_letter_model/g' tests/test_cover_letter_model_used.py && grep -c legacy_cover_letter_model tests/test_cover_letter_model_used.py
```

Expected output: `3`.

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_llm.py tests/test_cover_letter.py tests/test_cover_letter_model_used.py
```

Expected: `test_model_defaults` fails with `KeyError: 'writer_effort'`, and the cover-letter tests fail with `AttributeError: 'Settings' object has no attribute 'legacy_cover_letter_model'`.

- [ ] **Step 3a: Implement config.** In `/Users/admin/dev2/UpApply/api/app/core/config.py` replace these two lines (the second one was added by Phase 1 Task 1.2):

```python
    cover_letter_model: str = "claude-sonnet-4-6"
    extraction_model: str = "claude-haiku-4-5"   # fact extraction, job brief, claim check
```

with:

```python
    cover_letter_model: str = "claude-opus-5-5"            # generation v2 writer (no temperature/thinking params)
    legacy_cover_letter_model: str = "claude-sonnet-4-6"   # flag-off path; legacy calls still pass temperature
    extraction_model: str = "claude-haiku-4-5"             # job brief, claim check, fact extraction
    writer_effort: str = "high"                            # Opus 5.5 defaults to medium; set explicitly
```

- [ ] **Step 3b: Add usage logging to `/Users/admin/dev2/UpApply/api/app/services/llm.py`.** In `structured_call`, directly after the `try: response = await get_anthropic_client().messages.create(...) / except APIError` block and before the `stop_reason` check, insert (at function-body indentation):

```python
    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "llm model=%s in=%s out=%s cache_read=%s cache_write=%s",
            model,
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
            getattr(usage, "cache_read_input_tokens", None),
            getattr(usage, "cache_creation_input_tokens", None),
        )
```

- [ ] **Step 3c: Pin legacy callers.**

```bash
cd /Users/admin/dev2/UpApply/api && \
sed -i '' 's/model=model or settings\.cover_letter_model,/model=model or settings.legacy_cover_letter_model,/' app/services/cover_letter.py && \
sed -i '' 's/model=settings\.cover_letter_model,/model=settings.legacy_cover_letter_model,/' app/services/profile_optimizer.py app/api/v1/import_chatgpt.py && \
sed -i '' 's/model_used=settings\.cover_letter_model,/model_used=settings.legacy_cover_letter_model,/' app/api/v1/jobs.py && \
grep -rn "settings.cover_letter_model" app/ ; grep -rnc "legacy_cover_letter_model" app/services/cover_letter.py app/services/profile_optimizer.py app/api/v1/import_chatgpt.py app/api/v1/jobs.py
```

Expected: the first grep prints nothing (no caller still reads `settings.cover_letter_model`). Counts are `cover_letter.py:3`, `profile_optimizer.py:1`, `import_chatgpt.py:1`, `jobs.py:3`.

- [ ] **Step 4: Run and confirm pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_llm.py tests/test_fact_extraction.py tests/test_cover_letter.py tests/test_cover_letter_model_used.py tests/test_profile_optimizer.py
```

Expected: all passed, 0 failed.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add api/app/core/config.py api/app/services/llm.py api/app/services/cover_letter.py api/app/services/profile_optimizer.py api/app/api/v1/import_chatgpt.py api/app/api/v1/jobs.py api/tests/test_llm.py api/tests/test_cover_letter.py api/tests/test_cover_letter_model_used.py && git commit -m "$(cat <<'EOF'
feat(llm): Opus 5.5 model config, legacy pin, structured_call usage logging

cover_letter_model now defaults to claude-opus-5-5 for the v2 writer;
writer_effort ("high") and legacy_cover_letter_model are new.
Legacy generation, profile optimizer and ChatGPT import are pinned to
legacy_cover_letter_model because they pass temperature, which Opus 5.5
rejects. structured_call now logs token usage including cache reads/writes.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.2: Migration 023 — traceability columns and `generation_v2` flag

**Files:**
- Create: `api/alembic/versions/023_generation_v2.py`
- Create: `api/tests/test_generation_schema.py`
- Modify: `api/app/models/cover_letter.py:6-7` (imports), after line 60 (`is_final`)
- Modify: `api/app/models/user.py` after line 130 (`proposal_anchors`)

**Interfaces:**
- Consumes: Phase 1 Task 1.1 revision id `022_knowledge_layer` (whose `down_revision` is `021_global_signal_pool`, the current head). Chain: `021_global_signal_pool` → `022_knowledge_layer` → `023_generation_v2` → `024_refine_loop` (Phase 3 Task 3.1).
- Produces: `CoverLetter.brief: dict | None`, `CoverLetter.fact_ids_used: list[str] | None` (ARRAY(String(36))), `CoverLetter.voice_sample_ids: list[str] | None` (ARRAY(String(36))), `CoverLetter.verify_warnings: list[str] | None` (JSONB), `UserProfile.generation_v2: bool` (NOT NULL, server default false).

- [ ] **Step 1: Write the failing tests.** Create `/Users/admin/dev2/UpApply/api/tests/test_generation_schema.py`:

```python
"""Schema for generation v2: cover letter traceability + per-user flag (migration 023)."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.models.cover_letter import CoverLetter
from app.models.user import UserProfile

MIGRATION = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "023_generation_v2.py"


def test_cover_letter_traceability_columns():
    cols = CoverLetter.__table__.c
    assert isinstance(cols.brief.type, JSONB)
    assert isinstance(cols.fact_ids_used.type, ARRAY)
    assert isinstance(cols.voice_sample_ids.type, ARRAY)
    assert isinstance(cols.verify_warnings.type, JSONB)
    for name in ("brief", "fact_ids_used", "voice_sample_ids", "verify_warnings"):
        assert cols[name].nullable is True


def test_generation_v2_flag_is_not_null_default_false():
    col = UserProfile.__table__.c.generation_v2
    assert col.nullable is False
    assert col.server_default.arg.text == "false"


def test_migration_023_chains_onto_phase_1():
    spec = importlib.util.spec_from_file_location("m023", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "023_generation_v2"
    assert module.down_revision == "022_knowledge_layer"


@pytest.mark.asyncio
async def test_new_profiles_have_generation_v2_off(client, auth_headers_with_profile):
    from tests.conftest import test_engine

    async with test_engine.connect() as conn:
        value = (await conn.execute(text("SELECT generation_v2 FROM user_profiles"))).scalar_one()
    assert value is False
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_schema.py
```

Expected: 4 failed. The errors are `AttributeError: brief` / `generation_v2` from the column collection, `FileNotFoundError` for the migration file, and `ProgrammingError: column "generation_v2" does not exist`.

- [ ] **Step 3a: Model columns.** In `/Users/admin/dev2/UpApply/api/app/models/cover_letter.py` change the import line:

```python
from sqlalchemy.dialects.postgresql import JSONB
```

to:

```python
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
```

and insert after `is_final: Mapped[bool] = mapped_column(Boolean, default=False)`:

```python

    # Generation v2 traceability (migration 023) — what §3 learning scores against
    brief: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    fact_ids_used: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(36)), nullable=True)
    voice_sample_ids: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(36)), nullable=True)
    verify_warnings: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
```

In `/Users/admin/dev2/UpApply/api/app/models/user.py` change the sqlalchemy import line:

```python
from sqlalchemy import Boolean, DateTime, String, Text, Integer, Numeric, Date, func, ForeignKey
```

to:

```python
from sqlalchemy import Boolean, DateTime, String, Text, Integer, Numeric, Date, func, ForeignKey, text
```

and insert after `proposal_anchors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)`:

```python

    # Route cover letter + screening generation to the v2 engine (migration 023)
    generation_v2: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
```

- [ ] **Step 3b: Create `/Users/admin/dev2/UpApply/api/alembic/versions/023_generation_v2.py`:**

```python
"""Generation v2: cover letter traceability columns + per-user generation_v2 flag.

Revision ID: 023_generation_v2
Revises: 022_knowledge_layer
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB


revision = '023_generation_v2'
down_revision = '022_knowledge_layer'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('cover_letters', sa.Column('brief', JSONB, nullable=True))
    op.add_column('cover_letters', sa.Column('fact_ids_used', ARRAY(sa.String(36)), nullable=True))
    op.add_column('cover_letters', sa.Column('voice_sample_ids', ARRAY(sa.String(36)), nullable=True))
    op.add_column('cover_letters', sa.Column('verify_warnings', JSONB, nullable=True))
    op.add_column(
        'user_profiles',
        sa.Column('generation_v2', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('user_profiles', 'generation_v2')
    op.drop_column('cover_letters', 'verify_warnings')
    op.drop_column('cover_letters', 'voice_sample_ids')
    op.drop_column('cover_letters', 'fact_ids_used')
    op.drop_column('cover_letters', 'brief')
```

- [ ] **Step 4: Run and confirm pass, then exercise the migration on a scratch database**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_schema.py
```

Expected: `4 passed`.

```bash
PGPASSWORD=upapply psql -h localhost -p 55499 -U upapply -d postgres -c "DROP DATABASE IF EXISTS upapply_mig_p2" -c "CREATE DATABASE upapply_mig_p2" && \
PGPASSWORD=upapply psql -h localhost -p 55499 -U upapply -d upapply_mig_p2 -c "CREATE EXTENSION IF NOT EXISTS vector" && \
cd /Users/admin/dev2/UpApply/api && export DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_mig_p2 && \
./venv/bin/alembic upgrade head && ./venv/bin/alembic downgrade -1 && ./venv/bin/alembic upgrade head && ./venv/bin/alembic current
```

Expected: no errors, and the last line is `023_generation_v2 (head)`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add api/alembic/versions/023_generation_v2.py api/app/models/cover_letter.py api/app/models/user.py api/tests/test_generation_schema.py && git commit -m "$(cat <<'EOF'
feat(db): migration 023 - cover letter traceability + generation_v2 flag

cover_letters gains brief (JSONB), fact_ids_used and voice_sample_ids
(VARCHAR(36)[]), verify_warnings (JSONB). user_profiles gains
generation_v2 (NOT NULL, default false) so v2 can be enabled per user.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.3: Job brief (`generation/brief.py`)

**Files:**
- Create: `api/app/services/generation/__init__.py`
- Create: `api/app/services/generation/brief.py`
- Create: `api/tests/test_generation_brief.py`

**Interfaces:**
- Consumes: `structured_call` (Phase 1 Task 1.2), `settings.extraction_model` (Phase 1 Task 1.2).
- Produces: `JOB_TYPES: list[str]`, `BRIEF_SCHEMA: dict`, `class JobBrief(BaseModel)` with `needs, job_types, client_signals, mirror_phrases, explicit_asks, questions`, plus the additive `title: str = ""` and `description: str = ""`. The writer needs the full post, and Phase 3 refine re-sends the stored brief. `client_signals` keys are `complexity` (`terse|standard|complex`), `technical_depth`, `tone`, `worries`, and `red_flags`. `async build_job_brief(title: str, description: str, skills: list[str], questions: list[str]) -> JobBrief`.

- [ ] **Step 1: Write the failing tests.** Create `/Users/admin/dev2/UpApply/api/tests/test_generation_brief.py`:

```python
"""Generation v2 step 1: job brief."""
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.services.generation.brief import BRIEF_SCHEMA, JOB_TYPES, JobBrief, build_job_brief

MODEL_OUTPUT = {
    "needs": [
        "Has migrated production SQL Server to Azure without downtime",
        "Can own the data layer end to end",
    ],
    "job_types": ["sql", "cloud", "blockchain"],
    "client_signals": {
        "complexity": "standard",
        "technical_depth": "high",
        "tone": "direct",
        "worries": ["downtime during cutover"],
        "red_flags": [],
    },
    "mirror_phrases": ["zero downtime cutover"],
    "explicit_asks": ['Start your reply with "Azure"'],
}


@pytest.mark.asyncio
async def test_build_job_brief_uses_extraction_model_and_keeps_questions_verbatim():
    call = AsyncMock(return_value=dict(MODEL_OUTPUT))
    with patch("app.services.generation.brief.structured_call", call):
        brief = await build_job_brief(
            title="Azure SQL migration",
            description="We need a zero downtime cutover of 40 databases.",
            skills=["SQL Server", "Azure"],
            questions=["  Describe a similar migration.  "],
        )
    kwargs = call.call_args.kwargs
    assert kwargs["model"] == settings.extraction_model
    assert kwargs["schema"] is BRIEF_SCHEMA
    assert kwargs.get("effort") is None
    assert "We need a zero downtime cutover of 40 databases." in kwargs["user"]
    assert "SQL Server, Azure" in kwargs["user"]
    assert "Describe a similar migration." in kwargs["user"]

    assert isinstance(brief, JobBrief)
    assert brief.questions == ["  Describe a similar migration.  "]
    assert brief.job_types == ["sql", "cloud"]
    assert brief.client_signals["complexity"] == "standard"
    assert brief.mirror_phrases == ["zero downtime cutover"]
    assert brief.title == "Azure SQL migration"
    assert brief.description == "We need a zero downtime cutover of 40 databases."


@pytest.mark.asyncio
async def test_build_job_brief_caps_needs_at_six():
    output = dict(MODEL_OUTPUT, needs=[f"need {i}" for i in range(9)])
    with patch("app.services.generation.brief.structured_call", AsyncMock(return_value=output)):
        brief = await build_job_brief(title="t", description="d", skills=[], questions=[])
    assert brief.needs == [f"need {i}" for i in range(6)]
    assert brief.questions == []


def test_brief_schema_is_valid_for_structured_outputs():
    def walk(node):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                walk(child)
        if node.get("type") == "array":
            walk(node["items"])

    walk(BRIEF_SCHEMA)
    assert "questions" not in BRIEF_SCHEMA["properties"]
    assert BRIEF_SCHEMA["properties"]["job_types"]["items"]["enum"] == JOB_TYPES
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_brief.py
```

Expected: collection error `ModuleNotFoundError: No module named 'app.services.generation'`.

- [ ] **Step 3: Implement.** Create `/Users/admin/dev2/UpApply/api/app/services/generation/__init__.py`:

```python
"""Generation v2 engine: brief → evidence → write → verify (spec §2)."""
```

Create `/Users/admin/dev2/UpApply/api/app/services/generation/brief.py`:

```python
"""Generation v2 step 1: turn a job post into a structured brief (cheap model)."""
from pydantic import BaseModel

from app.core.config import settings
from app.services.llm import structured_call

JOB_TYPES = ["cto", "saas", "sql", "cloud", "ai", "fullstack"]
MAX_NEEDS = 6


def _str_list(description: str) -> dict:
    return {"type": "array", "items": {"type": "string"}, "description": description}


BRIEF_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "needs": _str_list("3-6 concrete things the client must come away believing about the freelancer"),
        "job_types": {
            "type": "array",
            "items": {"type": "string", "enum": JOB_TYPES},
            "description": "Every job type label that applies",
        },
        "client_signals": {
            "type": "object",
            "properties": {
                "complexity": {"type": "string", "enum": ["terse", "standard", "complex"]},
                "technical_depth": {"type": "string", "enum": ["low", "medium", "high"]},
                "tone": {"type": "string"},
                "worries": _str_list("What the client is anxious about"),
                "red_flags": _str_list("Scope, budget or fit concerns for the freelancer"),
            },
            "required": ["complexity", "technical_depth", "tone", "worries", "red_flags"],
            "additionalProperties": False,
        },
        "mirror_phrases": _str_list("Up to 6 of the client's own distinctive phrases, copied exactly"),
        "explicit_asks": _str_list("Every direct instruction to applicants, near-verbatim"),
    },
    "required": ["needs", "job_types", "client_signals", "mirror_phrases", "explicit_asks"],
    "additionalProperties": False,
}

BRIEF_SYSTEM = """You read Upwork job posts and brief a senior freelancer before they write a proposal. Be concrete and specific to this post; never generic.

- needs: 3-6 statements of what the client must come away believing about the freelancer, phrased as capabilities proven by past work (e.g. "has migrated production SQL Server to Azure without downtime"). Derive them from what the post actually says, not from the skills list alone. Most important first.
- job_types: every label that applies. cto = leadership, architecture, advisory, audits, fractional CTO. saas = building a new product or MVP. sql = database design, migration, tuning. cloud = Azure/AWS/GCP infrastructure, DevOps. ai = LLMs, RAG, ML, automation. fullstack = web or app development.
- client_signals.complexity: "terse" for short, simple posts; "complex" for long, multi-part or leadership posts; otherwise "standard". technical_depth is how technical the client is. tone is how they write (e.g. "casual and rushed", "formal and detailed"). worries: what they are anxious about. red_flags: scope, budget or fit concerns for the freelancer.
- mirror_phrases: up to 6 of the client's own distinctive words or phrases worth echoing, copied exactly.
- explicit_asks: every direct instruction to applicants (e.g. 'start your reply with "blue"', 'include your GitHub link'), copied as close to verbatim as possible, keeping any quoted words in double quotes. Empty list if none."""


class JobBrief(BaseModel):
    needs: list[str]
    job_types: list[str]
    client_signals: dict
    mirror_phrases: list[str]
    explicit_asks: list[str]
    questions: list[str]
    title: str = ""
    description: str = ""


async def build_job_brief(
    title: str,
    description: str,
    skills: list[str],
    questions: list[str],
) -> JobBrief:
    """Extract needs, job types, client signals and asks from a job post."""
    question_lines = "\n".join(f"{i}. {q.strip()}" for i, q in enumerate(questions, 1)) or "none"
    user = (
        f"JOB TITLE: {title}\n\n"
        f"SKILLS LISTED: {', '.join(skills) or 'none'}\n\n"
        f"JOB POST:\n{description}\n\n"
        f"SCREENING QUESTIONS:\n{question_lines}"
    )
    data = await structured_call(
        model=settings.extraction_model,
        system=BRIEF_SYSTEM,
        user=user,
        schema=BRIEF_SCHEMA,
        max_tokens=4000,
    )
    return JobBrief(
        needs=[n for n in data.get("needs", []) if n.strip()][:MAX_NEEDS],
        job_types=[jt for jt in data.get("job_types", []) if jt in JOB_TYPES],
        client_signals=data.get("client_signals", {}),
        mirror_phrases=data.get("mirror_phrases", []),
        explicit_asks=data.get("explicit_asks", []),
        questions=list(questions),
        title=title,
        description=description,
    )
```

- [ ] **Step 4: Run and confirm pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_brief.py
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add api/app/services/generation/__init__.py api/app/services/generation/brief.py api/tests/test_generation_brief.py && git commit -m "$(cat <<'EOF'
feat(generation): job brief step on extraction model

build_job_brief turns a job post into needs, multi-label job_types,
client_signals (incl. complexity for length), mirror phrases and
explicit asks via a strict structured-output schema. Screening
questions are carried verbatim, never trusted from the model.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.4: Evidence retrieval with rerank (`generation/evidence.py`)

**Files:**
- Create: `api/app/services/generation/evidence.py`
- Create: `api/tests/test_generation_evidence.py`

**Interfaces:**
- Consumes: `search_facts(db, user_id, query_embedding, limit=8, status='approved') -> list[tuple[Fact, float]]` (Phase 1); `generate_embeddings_batch(texts) -> list[list[float]]` (`app/core/embeddings.py:105`); `Proposal.author`, `Proposal.outcome`, `Proposal.job_needs_embedding` (Phase 1); `JobBrief`.
- Produces: `rerank_score(similarity, strength, times_used, times_in_won) -> float`; `@dataclass Evidence(facts: list[Fact], voice_samples: list[Proposal])`; `format_facts(facts) -> str`; `async select_evidence(db, user_id, brief, anchors) -> Evidence`; private `_select_facts`, `_find_voice_samples(db, user_id, query_embedding, limit=3)`.
- Voice-sample query vector: the embedding of `"{brief.title}\n\n{brief.description}"` (the same text shape Phase 1 Task 1.8 and Phase 3 Task 3.4 embed into `job_needs_embedding`), so the comparison is job against job. When the brief has neither title nor description it falls back to `"\n".join(brief.needs)`.
- Always-include floor: each `profile.proposal_anchors["always_include"]` string is embedded and resolved to its nearest approved fact. The fact is added when similarity ≥ 0.75, beyond the 8-fact cap. Every claim therefore still traces to a fact id.

- [ ] **Step 1: Write the failing tests.** Create `/Users/admin/dev2/UpApply/api/tests/test_generation_evidence.py`:

```python
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
    embed = AsyncMock(return_value=[[1.0], [2.0], [3.0], [4.0]])
    with patch.object(ev, "generate_embeddings_batch", embed), \
         patch.object(ev, "search_facts", AsyncMock(side_effect=fake_search)), \
         patch.object(ev, "_find_voice_samples", AsyncMock(return_value=voice)) as find_voice:
        result = await select_evidence(
            db=None, user_id="u1", brief=_brief(["need one", "need two"]),
            anchors={"always_include": ["160-server migration"], "sql": "ignored here"},
        )
    assert embed.call_args.args[0] == ["need one", "need two", "160-server migration", "need one\nneed two"]
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
    assert embed.call_args.args[0] == ["need one", "Azure lead\n\nMigrate our SQL estate"]


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
        await db.rollback()
    assert [s.cover_letter_text for s in samples] == ["Chris edited, hired", "Chris exact, no response"]
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_evidence.py
```

Expected: collection error `ModuleNotFoundError: No module named 'app.services.generation.evidence'`.

- [ ] **Step 3: Implement.** Create `/Users/admin/dev2/UpApply/api/app/services/generation/evidence.py`:

```python
"""Generation v2 step 2: choose the facts and voice samples a draft may use (no LLM)."""
import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import generate_embeddings_batch
from app.models.fact import Fact
from app.models.proposal import Proposal
from app.services.facts import search_facts
from app.services.generation.brief import JobBrief

logger = logging.getLogger(__name__)

PER_NEED_CANDIDATES = 8
MIN_FACTS = 4
MAX_FACTS = 8
FILL_MIN_SCORE = 0.55
ANCHOR_MIN_SIMILARITY = 0.75
VOICE_SAMPLE_LIMIT = 3
VOICE_AUTHORS = ("chris", "chris_edited_ai")
OUTCOME_BOOST = {"hired": 0.15, "interviewed": 0.10, "replied": 0.08, "viewed": 0.02}


def rerank_score(similarity: float, strength: float, times_used: int, times_in_won: int) -> float:
    """0.55·similarity + 0.25·strength + 0.20·win_signal, win_signal Laplace-smoothed."""
    win_signal = (times_in_won + 1) / (times_used + 2)
    return 0.55 * similarity + 0.25 * strength + 0.20 * win_signal


@dataclass
class Evidence:
    facts: list[Fact] = field(default_factory=list)
    voice_samples: list[Proposal] = field(default_factory=list)


def format_facts(facts: list[Fact]) -> str:
    """Render facts as `[id] (kind) statement` lines; ids are what the writer cites."""
    if not facts:
        return "(no approved facts matched this job)"
    lines = []
    for fact in facts:
        lines.append(f"[{fact.id}] ({fact.kind}) {fact.statement}")
        if fact.detail:
            lines.append(f"    {fact.detail}")
    return "\n".join(lines)


def _select_facts(per_need: list[list[tuple[Fact, float]]]) -> list[Fact]:
    """Best unseen fact per need first, then fill by global score (4-8 total)."""
    scored = [
        sorted(
            (
                (fact, rerank_score(sim, fact.strength or 0.0, fact.times_used or 0, fact.times_in_won or 0))
                for fact, sim in candidates
            ),
            key=lambda pair: pair[1],
            reverse=True,
        )
        for candidates in per_need
    ]

    chosen: list[Fact] = []
    seen: set[str] = set()
    for ranked in scored:
        if len(chosen) >= MAX_FACTS:
            break
        for fact, _ in ranked:
            if str(fact.id) not in seen:
                chosen.append(fact)
                seen.add(str(fact.id))
                break

    pool = sorted((pair for ranked in scored for pair in ranked), key=lambda pair: pair[1], reverse=True)
    for fact, score in pool:
        if len(chosen) >= MAX_FACTS:
            break
        if str(fact.id) in seen:
            continue
        if len(chosen) >= MIN_FACTS and score < FILL_MIN_SCORE:
            break
        chosen.append(fact)
        seen.add(str(fact.id))
    return chosen


async def _find_voice_samples(
    db: AsyncSession,
    user_id: str,
    query_embedding: list[float],
    limit: int = VOICE_SAMPLE_LIMIT,
) -> list[Proposal]:
    """Chris-written proposals for similar jobs, nudged toward ones that got traction."""
    distance = Proposal.job_needs_embedding.cosine_distance(query_embedding)
    stmt = (
        select(Proposal, (1 - distance).label("similarity"))
        .where(
            Proposal.user_id == user_id,
            Proposal.author.in_(VOICE_AUTHORS),
            Proposal.job_needs_embedding.isnot(None),
        )
        .order_by(distance)
        .limit(limit * 4)
    )
    rows = (await db.execute(stmt)).all()
    ranked = sorted(
        rows,
        key=lambda row: row.similarity + OUTCOME_BOOST.get(row.Proposal.outcome or "", 0.0),
        reverse=True,
    )
    return [row.Proposal for row in ranked[:limit]]


async def select_evidence(
    db: AsyncSession,
    user_id: str,
    brief: JobBrief,
    anchors: Optional[dict],
) -> Evidence:
    """Per-need fact retrieval + rerank, always-include floor, and 2-3 voice samples."""
    needs = [n for n in brief.needs if n.strip()]
    always = [a for a in ((anchors or {}).get("always_include") or []) if isinstance(a, str) and a.strip()]
    # Job<->job: same text shape Phase 1 (Task 1.8) and Phase 3 (Task 3.4) embed into
    # proposals.job_needs_embedding ("title\n\ndescription"); needs are the fallback.
    voice_query = "\n\n".join(t for t in (brief.title, brief.description) if t) or "\n".join(needs)
    texts = needs + always + ([voice_query] if voice_query else [])
    if not texts:
        return Evidence()

    try:
        vectors = await generate_embeddings_batch(texts)
    except Exception as exc:
        logger.warning("Embeddings unavailable for evidence selection: %s", exc)
        return Evidence()

    need_vectors = vectors[: len(needs)]
    anchor_vectors = vectors[len(needs) : len(needs) + len(always)]

    per_need = [await search_facts(db, user_id, vec, limit=PER_NEED_CANDIDATES) for vec in need_vectors]
    facts = _select_facts(per_need)
    seen = {str(f.id) for f in facts}

    for vec in anchor_vectors:
        hits = await search_facts(db, user_id, vec, limit=1)
        if hits and hits[0][1] >= ANCHOR_MIN_SIMILARITY and str(hits[0][0].id) not in seen:
            facts.append(hits[0][0])
            seen.add(str(hits[0][0].id))

    voice = await _find_voice_samples(db, user_id, vectors[-1]) if voice_query else []
    return Evidence(facts=facts, voice_samples=voice)
```

- [ ] **Step 4: Run and confirm pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_evidence.py
```

Expected: `12 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add api/app/services/generation/evidence.py api/tests/test_generation_evidence.py && git commit -m "$(cat <<'EOF'
feat(generation): evidence selection with outcome-aware rerank

Per brief need: top-8 approved facts, reranked by
0.55*sim + 0.25*strength + 0.20*smoothed win rate; best unseen fact per
need, then fill to 4-8. always_include anchors resolve to approved facts
(sim >= 0.75) as a credential floor. Voice samples are chris /
chris_edited_ai proposals matched job-to-job and boosted by outcome.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.5: Verify — deterministic rules and claim check (`generation/verify.py`)

**Files:**
- Create: `api/app/services/generation/verify.py`
- Create: `api/tests/test_generation_verify.py`
- Modify: `api/app/services/cover_letter.py` (add the `BANNED_PHRASES` constant after the imports, ~line 11; the legacy prompt text stays unchanged)

**Interfaces:**
- Consumes: `JobBrief`, `Evidence`, `format_facts`, `structured_call`, `settings.extraction_model`. Any object with `.cover_letter` / `.screening_answers` (the `Draft` from Task 2.6) is accepted.
- Produces: `BANNED_PHRASES: list[str]` (in `cover_letter.py`); `LENGTH_TARGETS: dict[str, tuple[int, int]]`; `length_band(brief) -> tuple[int, int]`; `expected_closing(preferred_closing: str | None) -> str`; `check_rules(text: str, brief: JobBrief, preferred_closing: str | None) -> list[str]`; `CLAIM_CHECK_SKIPPED: str`; `async check_claims(draft, evidence: Evidence) -> list[str]`.
- Closing rule: the letter ends with `Warm regards,` followed by `\n{preferred_closing}` when one is set. If `preferred_closing` itself starts with "Warm regards", it is used as-is.

- [ ] **Step 1: Write the failing tests.** Create `/Users/admin/dev2/UpApply/api/tests/test_generation_verify.py`:

```python
"""Generation v2 step 4: deterministic rules + claim audit."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.services.cover_letter import BANNED_PHRASES, build_system_prompt
from app.services.generation.brief import JobBrief
from app.services.generation.evidence import Evidence
from app.services.generation.verify import (
    CLAIM_CHECK_SKIPPED,
    check_claims,
    check_rules,
    expected_closing,
    length_band,
)

SENTENCE = "Your migration plan needs a rollback path that was proven on a live estate."  # 14 words


def _brief(complexity="standard", asks=None):
    return JobBrief(
        needs=["x"], job_types=[], client_signals={"complexity": complexity},
        mirror_phrases=[], explicit_asks=asks or [], questions=[],
    )


def _letter(sentences=17, extra="", closing="Warm regards,"):
    body = " ".join([SENTENCE] * sentences) + extra
    return f"{body}\n\n{closing}"


def test_clean_letter_passes():
    assert check_rules(_letter(), _brief(), None) == []


def test_expected_closing_variants():
    assert expected_closing(None) == "Warm regards,"
    assert expected_closing("Chris") == "Warm regards,\nChris"
    assert expected_closing("Warm regards,\nChris T.") == "Warm regards,\nChris T."


def test_missing_closing_is_flagged():
    violations = check_rules(_letter(closing="Best,"), _brief(), None)
    assert any('end with "Warm regards,"' in v for v in violations)


def test_preferred_closing_must_follow_warm_regards():
    assert check_rules(_letter(closing="Warm regards,\nChris"), _brief(), "Chris") == []
    assert check_rules(_letter(), _brief(), "Chris") != []


def test_salutation_is_flagged():
    violations = check_rules("Hi there,\n" + _letter(), _brief(), None)
    assert any("salutation" in v for v in violations)


def test_sentence_starting_with_i_is_flagged_but_in_and_it_are_not():
    assert check_rules(_letter(extra=" In practice it holds. It works."), _brief(), None) == []
    violations = check_rules(_letter(extra=" I have done this before. I'm sure."), _brief(), None)
    assert sum('starts with "I"' in v for v in violations) == 2


def test_banned_phrase_is_flagged():
    violations = check_rules(_letter(extra=" We can leverage my expertise here."), _brief(), None)
    assert any("leverage my expertise" in v for v in violations)


def test_length_band_is_job_driven():
    assert length_band(_brief("terse")) == (150, 250)
    assert length_band(_brief("complex")) == (300, 450)
    assert length_band(_brief("unknown")) == (200, 350)
    short = check_rules(_letter(sentences=4), _brief("standard"), None)
    assert any("Length" in v for v in short)
    assert check_rules(_letter(sentences=28), _brief("complex"), None) == []


def test_quoted_explicit_ask_must_be_honoured():
    ask = 'Start your reply with "Azure"'
    assert any("Explicit ask" in v for v in check_rules(_letter(), _brief(asks=[ask]), None))
    assert check_rules("Azure first. " + _letter(), _brief(asks=[ask]), None) == []


def test_banned_phrases_constant_matches_legacy_prompt():
    profile = SimpleNamespace(
        full_name=None, professional_title=None, bio=None, career_goals=None,
        communication_style=None, unique_strengths=None, proposal_anchors=None,
    )
    prompt = build_system_prompt(profile)
    assert len(BANNED_PHRASES) == 14
    for phrase in BANNED_PHRASES:
        assert phrase in prompt


FACT = SimpleNamespace(id="fact-1", kind="metric", statement="Cut report runtime from 40 min to 90 s.", detail=None)


@pytest.mark.asyncio
async def test_check_claims_reports_unsupported_claims():
    draft = SimpleNamespace(
        cover_letter="Saved a client $2M last year.\n\nWarm regards,",
        screening_answers=[{"question": "Q?", "answer": "Report runtime went from 40 min to 90 s."}],
    )
    call = AsyncMock(return_value={"unsupported_claims": [{"claim": "Saved a client $2M", "reason": "no matching fact"}]})
    with patch("app.services.generation.verify.structured_call", call):
        warnings = await check_claims(draft, Evidence(facts=[FACT]))
    assert warnings == ["Unsupported claim: Saved a client $2M (no matching fact)"]
    kwargs = call.call_args.kwargs
    assert kwargs["model"] == settings.extraction_model
    assert "[fact-1] (metric) Cut report runtime from 40 min to 90 s." in kwargs["user"]
    assert "Saved a client $2M last year." in kwargs["user"]
    assert "Report runtime went from 40 min to 90 s." in kwargs["user"]


@pytest.mark.asyncio
async def test_check_claims_degrades_to_skip_marker_on_llm_failure():
    draft = SimpleNamespace(cover_letter="x", screening_answers=[])
    with patch("app.services.generation.verify.structured_call", AsyncMock(side_effect=RuntimeError("down"))):
        assert await check_claims(draft, Evidence()) == [CLAIM_CHECK_SKIPPED]
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_verify.py
```

Expected: collection error `ImportError: cannot import name 'BANNED_PHRASES' from 'app.services.cover_letter'`.

- [ ] **Step 3a: Add the shared constant.** In `/Users/admin/dev2/UpApply/api/app/services/cover_letter.py` insert after `from app.schemas.job import SkillMatch` (line 10):

```python


# Phrases that signal generic AI writing. Mirrors the BANNED PHRASES block in
# build_system_prompt (legacy, left untouched); generation v2 enforces this list.
BANNED_PHRASES = [
    "I am well-equipped",
    "unique blend of skills",
    "align perfectly with your needs",
    "I am excited to apply",
    "I look forward to hearing from you",
    "my skills directly translate",
    "I am passionate about",
    "leverage my expertise",
    "I believe I would be a great fit",
    "I am confident that",
    "I would love the opportunity",
    "I am a perfect fit",
    "I am writing to",
    "I am reaching out",
]
```

- [ ] **Step 3b: Create `/Users/admin/dev2/UpApply/api/app/services/generation/verify.py`:**

```python
"""Generation v2 step 4: deterministic rule checks and a cheap-model claim audit."""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional

from app.core.config import settings
from app.services.cover_letter import BANNED_PHRASES
from app.services.generation.brief import JobBrief
from app.services.generation.evidence import Evidence, format_facts
from app.services.llm import structured_call

if TYPE_CHECKING:
    from app.services.generation.writer import Draft

logger = logging.getLogger(__name__)

WARM_REGARDS = "Warm regards,"
LENGTH_TARGETS = {"terse": (150, 250), "standard": (200, 350), "complex": (300, 450)}
LENGTH_SLACK = 0.10
CLAIM_CHECK_SKIPPED = "Claim check skipped (verifier unavailable) - review specifics manually."

_SALUTATION = re.compile(r"^(hello|hi|hey|dear|greetings|good (morning|afternoon|evening)|subject:)\b", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_STARTS_WITH_I = re.compile(r"^[\"'“‘(\-–—*\s]*I\b")
_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")

CLAIMS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "unsupported_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"claim": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["claim", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["unsupported_claims"],
    "additionalProperties": False,
}

CLAIMS_SYSTEM = """You audit freelance proposals for claims the writer cannot back up.

A claim is any specific statement about the writer's own past: a number or metric, a named client or company, a named project or product, a credential, a team size, a duration, or a concrete outcome. A claim is supported only if an EVIDENCE item states it (paraphrase is fine; changed numbers are not).

Not claims: statements of approach or intent ("would start by profiling the slowest queries"), general professional opinions, and anything that restates the client's own job post.

Return every unsupported claim, quoting the shortest exact span from the draft, with a one-line reason. Return an empty list when everything is supported."""


def length_band(brief: JobBrief) -> tuple[int, int]:
    return LENGTH_TARGETS.get(brief.client_signals.get("complexity"), LENGTH_TARGETS["standard"])


def expected_closing(preferred_closing: Optional[str]) -> str:
    closing = (preferred_closing or "").strip()
    if closing.lower().startswith("warm regards"):
        return closing
    return f"{WARM_REGARDS}\n{closing}" if closing else WARM_REGARDS


def check_rules(text: str, brief: JobBrief, preferred_closing: Optional[str]) -> list[str]:
    """Chris's hard rules. Returns human-readable violations (empty = clean)."""
    violations: list[str] = []
    stripped = text.strip()
    closing = expected_closing(preferred_closing)
    if stripped.endswith(closing):
        body = stripped[: -len(closing)].strip()
    else:
        violations.append(f'Letter must end with "{closing}".')
        body = stripped

    first_line = body.splitlines()[0].strip() if body else ""
    if _SALUTATION.match(first_line):
        violations.append("Letter opens with a salutation; start with content.")

    for sentence in _SENTENCE_SPLIT.split(body):
        sentence = sentence.strip()
        if _STARTS_WITH_I.match(sentence):
            violations.append(f'Sentence starts with "I": "{sentence[:80]}"')

    lowered = body.lower()
    for phrase in BANNED_PHRASES:
        if phrase.lower() in lowered:
            violations.append(f'Banned phrase used: "{phrase}"')

    low, high = length_band(brief)
    words = len(body.split())
    if words < int(low * (1 - LENGTH_SLACK)) or words > int(high * (1 + LENGTH_SLACK)):
        violations.append(f"Length {words} words is outside the {low}-{high} target for this job.")

    for ask in brief.explicit_asks:
        for quoted in _QUOTED.findall(ask):
            if quoted.lower() not in lowered:
                violations.append(f"Explicit ask not honoured: {ask}")
                break

    return violations


async def check_claims(draft: "Draft", evidence: Evidence) -> list[str]:
    """Every specific in the letter and answers must map to a provided fact."""
    answers = "\n\n".join(
        f"Q: {item.get('question', '')}\nA: {item.get('answer', '')}" for item in draft.screening_answers
    ) or "(none)"
    user = (
        f"EVIDENCE:\n{format_facts(evidence.facts)}\n\n"
        f"DRAFT LETTER:\n{draft.cover_letter}\n\n"
        f"SCREENING ANSWERS:\n{answers}"
    )
    try:
        data = await structured_call(
            model=settings.extraction_model,
            system=CLAIMS_SYSTEM,
            user=user,
            schema=CLAIMS_SCHEMA,
            max_tokens=4000,
        )
    except Exception as exc:
        logger.warning("Claim check failed: %s", exc)
        return [CLAIM_CHECK_SKIPPED]
    return [
        f"Unsupported claim: {item['claim']} ({item['reason']})"
        for item in data.get("unsupported_claims", [])
    ]
```

- [ ] **Step 4: Run and confirm pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_verify.py tests/test_cover_letter.py
```

Expected: all passed (12 in `test_generation_verify.py`), 0 failed.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add api/app/services/cover_letter.py api/app/services/generation/verify.py api/tests/test_generation_verify.py && git commit -m "$(cat <<'EOF'
feat(generation): verify step - hard rules + claim audit

check_rules enforces closing (Warm regards, + preferred_closing), no
salutation, no sentence starting with "I", banned phrases (shared
BANNED_PHRASES constant), job-driven length band and quoted explicit
asks. check_claims asks the extraction model to flag any specific not
backed by a provided fact; verifier outage yields a skip marker.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.6: Writer — joint letter + answers on Opus 5.5 (`generation/writer.py`)

**Files:**
- Create: `api/app/services/generation/writer.py`
- Create: `api/tests/test_generation_writer.py`

**Interfaces:**
- Consumes: `structured_call`, `settings.cover_letter_model`, `settings.writer_effort`, `clean_cover_letter`, `format_inclusions`, `BANNED_PHRASES` (`cover_letter.py`), `expected_closing` and `length_band` (verify), `format_facts` and `Evidence` (evidence), `JobBrief`.
- Produces: `class Draft(BaseModel): cover_letter: str, screening_answers: list[dict], fact_ids_used: list[str]`; `WRITER_SCHEMA`; `finalize_letter(raw: str, preferred_closing: str | None) -> str` (also used by Phase 3 refine); `build_writer_system(profile) -> str`, a job-independent string sent as one cached system block; `async write_application(profile, brief, evidence, include_call_offer, prototype_url, extra_points, repair_notes=None) -> Draft`.
- Post-processing: `clean_cover_letter` strips salutations and placeholders. Any model-written sign-off is removed and `expected_closing(profile.preferred_closing)` is appended. `fact_ids_used` is deduped and filtered to ids present in evidence. Answers are aligned to `brief.questions` order.

- [ ] **Step 1: Write the failing tests.** Create `/Users/admin/dev2/UpApply/api/tests/test_generation_writer.py`:

```python
"""Generation v2 step 3: writer call shape and post-processing."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.services.cover_letter import BANNED_PHRASES
from app.services.generation.brief import JobBrief
from app.services.generation.evidence import Evidence
from app.services.generation.writer import WRITER_SCHEMA, Draft, build_writer_system, write_application

PROFILE = SimpleNamespace(
    full_name="Chris Therriault",
    professional_title="Fractional CTO",
    career_goals="Build durable SaaS products",
    communication_style="Direct, peer-level",
    preferred_closing="Chris",
)
BRIEF = JobBrief(
    needs=["Has migrated SQL Server to Azure without downtime"],
    job_types=["sql", "cloud"],
    client_signals={"complexity": "standard", "technical_depth": "high", "tone": "direct",
                    "worries": ["downtime"], "red_flags": []},
    mirror_phrases=["zero downtime cutover"],
    explicit_asks=['Start your reply with "Azure"'],
    questions=["Describe a similar migration.", "What is your availability?"],
    title="Azure SQL migration",
    description="Full post text about a zero downtime cutover of 40 databases.",
)
FACT = SimpleNamespace(
    id="fact-1", kind="project", statement="Led a 160-server on-prem to Azure migration.",
    detail="Consolidated the distributed SQL estate.", strength=0.9, times_used=0, times_in_won=0,
)
VOICE = SimpleNamespace(
    id="prop-1", cover_letter_text="Your cutover worry is the right one to have.",
    job_title="SQL consolidation", outcome="hired",
)
EVIDENCE = Evidence(facts=[FACT], voice_samples=[VOICE])
MODEL_JSON = {
    "cover_letter": "Hello,\nAzure cutovers fail at the data layer.\n\nWarm regards,\nChris",
    "screening_answers": [
        {"question": "What is your availability?", "answer": "Twenty hours a week."},
        {"question": "Describe a similar migration.", "answer": "The 160-server move ran in waves."},
    ],
    "fact_ids_used": ["fact-1", "fact-1", "invented-9"],
}


async def _write(**overrides):
    args = dict(include_call_offer=True, prototype_url="https://demo.example.com",
                extra_points='"fixed-fee discovery"')
    args.update(overrides)
    call = AsyncMock(return_value=dict(MODEL_JSON))
    with patch("app.services.generation.writer.structured_call", call):
        draft = await write_application(PROFILE, BRIEF, EVIDENCE, **args)
    return draft, call.call_args.kwargs


@pytest.mark.asyncio
async def test_writer_call_uses_opus_effort_and_cached_system():
    _, kwargs = await _write()
    assert kwargs["model"] == settings.cover_letter_model
    assert kwargs["effort"] == settings.writer_effort
    assert kwargs["schema"] is WRITER_SCHEMA
    system = kwargs["system"]
    assert isinstance(system, list) and len(system) == 1
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert system[0]["text"] == build_writer_system(PROFILE)
    assert "Chris Therriault" in system[0]["text"]
    assert BRIEF.description not in system[0]["text"]
    for phrase in BANNED_PHRASES:
        assert phrase in system[0]["text"]


@pytest.mark.asyncio
async def test_writer_user_prompt_carries_job_evidence_voice_and_options():
    _, kwargs = await _write()
    user = kwargs["user"]
    assert BRIEF.description in user
    assert "Has migrated SQL Server to Azure without downtime" in user
    assert "zero downtime cutover" in user
    assert 'Start your reply with "Azure"' in user
    assert "[fact-1] (project) Led a 160-server on-prem to Azure migration." in user
    assert "Consolidated the distributed SQL estate." in user
    assert VOICE.cover_letter_text in user and "outcome: hired" in user
    assert "200-350 words" in user
    assert "free, no-commitment call" in user
    assert "https://demo.example.com" in user
    assert "fixed-fee discovery" in user
    assert "1. Describe a similar migration." in user
    assert "2. What is your availability?" in user


@pytest.mark.asyncio
async def test_writer_post_processing():
    draft, _ = await _write()
    assert isinstance(draft, Draft)
    assert draft.cover_letter == "Azure cutovers fail at the data layer.\n\nWarm regards,\nChris"
    assert draft.fact_ids_used == ["fact-1"]
    assert draft.screening_answers == [
        {"question": "Describe a similar migration.", "answer": "The 160-server move ran in waves."},
        {"question": "What is your availability?", "answer": "Twenty hours a week."},
    ]


@pytest.mark.asyncio
async def test_writer_job_with_no_screening_questions_returns_no_answers():
    """Review focus: most posts have no questions; stray model answers must not leak through."""
    no_questions = BRIEF.model_copy(update={"questions": []})
    call = AsyncMock(return_value=dict(MODEL_JSON))  # model still returns two answers
    with patch("app.services.generation.writer.structured_call", call):
        draft = await write_application(PROFILE, no_questions, EVIDENCE, True, None, None)
    assert draft.screening_answers == []
    assert "SCREENING QUESTIONS: none; return an empty screening_answers list." in call.call_args.kwargs["user"]
    assert draft.cover_letter.endswith("Warm regards,\nChris")


@pytest.mark.asyncio
async def test_writer_without_call_offer_or_prototype_and_with_repair_notes():
    _, kwargs = await _write(
        include_call_offer=False, prototype_url=None, extra_points=None,
        repair_notes=['Sentence starts with "I": "I led it"'],
    )
    user = kwargs["user"]
    assert "Do not offer a call" in user
    assert "PROTOTYPE" not in user
    assert "EXTRA POINTS" not in user
    assert 'Sentence starts with "I": "I led it"' in user
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_writer.py
```

Expected: collection error `ModuleNotFoundError: No module named 'app.services.generation.writer'`.

- [ ] **Step 3: Implement.** Create `/Users/admin/dev2/UpApply/api/app/services/generation/writer.py`:

```python
"""Generation v2 step 3: one writing-model call produces the letter and screening answers together."""
import re
from typing import Optional

from pydantic import BaseModel

from app.core.config import settings
from app.services.cover_letter import BANNED_PHRASES, clean_cover_letter, format_inclusions
from app.services.generation.brief import JobBrief
from app.services.generation.evidence import Evidence, format_facts
from app.services.generation.verify import expected_closing, length_band
from app.services.llm import structured_call


class Draft(BaseModel):
    cover_letter: str
    screening_answers: list[dict]
    fact_ids_used: list[str]


WRITER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "cover_letter": {"type": "string", "description": "Letter body only, no sign-off"},
        "screening_answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"question": {"type": "string"}, "answer": {"type": "string"}},
                "required": ["question", "answer"],
                "additionalProperties": False,
            },
        },
        "fact_ids_used": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["cover_letter", "screening_answers", "fact_ids_used"],
    "additionalProperties": False,
}

_TRAILING_SIGNOFF = re.compile(
    r"\n+\s*(warm regards|best regards|kind regards|regards|best|sincerely|thanks|thank you),?\s*"
    r"(\n[^\n]{0,60}){0,2}\s*$",
    re.IGNORECASE,
)


def finalize_letter(raw: str, preferred_closing: Optional[str]) -> str:
    """Strip salutations/placeholders and any model-written sign-off, then append the
    exact closing in code. Shared with the Phase 3 refine thread."""
    body = _TRAILING_SIGNOFF.sub("", clean_cover_letter(raw or "")).strip()
    return f"{body}\n\n{expected_closing(preferred_closing)}"


def build_writer_system(profile) -> str:
    """Stable per user (no job content) so it is served from the prompt cache."""
    name = profile.full_name or "the freelancer"
    title = profile.professional_title or "senior technical professional"
    banned = "\n".join(f'- "{phrase}"' for phrase in BANNED_PHRASES)
    parts = [
        f"You write Upwork proposals and screening answers as {name}, a {title}. "
        f"{name} is a senior technical peer deciding whether an engagement is worth their time, "
        "not an applicant asking for a chance."
    ]
    if profile.career_goals:
        parts.append(f"WHAT THEY CARE ABOUT: {profile.career_goals}")
    if profile.communication_style:
        parts.append(f"THEIR STYLE NOTES: {profile.communication_style}")
    parts.append(f"""HOW TO WRITE
- The VOICE SAMPLES in each request are real letters {name} sent. They are the primary style guide: match their rhythm, sentence length, directness and vocabulary. Never copy their sentences or reuse their structure.
- Open on the client's problem in the client's own words; use the MIRROR PHRASES where they fit naturally.
- Prove fit with the EVIDENCE facts that answer the client's NEEDS, using their names, numbers and outcomes exactly as stated.
- Make one concrete "here's how I'd start" move specific to this job.
- Then stop. There is no template: vary the shape, opening and paragraphing from letter to letter.
- Honour every EXPLICIT ASK from the client exactly.

NO FACT, NO CLAIM
- Every specific about {name}'s experience (numbers, client names, project or product names, credentials, team sizes, durations, outcomes) must come from the EVIDENCE block. If the evidence does not support it, leave it out. Never invent, inflate or round numbers.
- Put the id of every evidence fact you drew on, in the letter or the answers, in fact_ids_used.

HARD RULES (violations are failures)
- No sentence may begin with the word "I" (including I'm, I've, I'd, I'll). Restructure instead: "I built the pipeline" becomes "The pipeline was built..." or "Building that pipeline meant...".
- No salutation. Never start with Hello, Hi, Hey, Dear, Greetings or a Subject line; start with content.
- Do not write a sign-off, closing line or signature. The closing is added automatically.
- No placeholders such as [Client Name].
- Never use these phrases:
{banned}

SCREENING ANSWERS
- Answer every question, in order, copying each question text exactly into the question field.
- 2-5 sentences each unless the question asks for more. Draw on the same evidence as the letter, but prefer a different fact than the one the letter leans on when another fits.
- Same voice. The salutation, placeholder and banned-phrase rules apply to answers too.""")
    return "\n\n".join(parts)


def _format_voice_samples(samples) -> str:
    if not samples:
        return "(no voice samples available; write plainly and directly)"
    blocks = []
    for i, sample in enumerate(samples, 1):
        header = f"--- Sample {i}"
        if sample.outcome:
            header += f" (outcome: {sample.outcome})"
        if sample.job_title:
            header += f' for "{sample.job_title}"'
        blocks.append(f"{header}\n{sample.cover_letter_text.strip()}")
    return "\n\n".join(blocks)


def _format_signals(signals: dict) -> str:
    items = []
    for key, value in signals.items():
        if isinstance(value, list):
            value = ", ".join(value)
        if value:
            items.append(f"{key.replace('_', ' ')}: {value}")
    return "; ".join(items) or "none noted"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- none"


def build_writer_user_prompt(
    profile,
    brief: JobBrief,
    evidence: Evidence,
    include_call_offer: bool,
    prototype_url: Optional[str],
    extra_points: Optional[str],
    repair_notes: Optional[list[str]],
) -> str:
    name = profile.full_name or "the freelancer"
    low, high = length_band(brief)
    parts = [
        f"JOB TITLE: {brief.title}",
        f"JOB POST:\n{brief.description}",
        f"NEEDS (what the client must come away believing):\n{_bullets(brief.needs)}",
        f"CLIENT SIGNALS: {_format_signals(brief.client_signals)}",
        f"MIRROR PHRASES:\n{_bullets(brief.mirror_phrases)}",
        f"EXPLICIT ASKS (honour every one):\n{_bullets(brief.explicit_asks)}",
        f"EVIDENCE (the only source of specifics about {name}):\n{format_facts(evidence.facts)}",
        f"VOICE SAMPLES (real letters {name} sent; write the way these read):\n"
        f"{_format_voice_samples(evidence.voice_samples)}",
        f"LENGTH: aim for {low}-{high} words in the letter body.",
    ]
    if include_call_offer:
        parts.append(
            "CALL OFFER: somewhere natural near the end, offer a free, no-commitment call, "
            "in your own words, in one sentence."
        )
    else:
        parts.append("CALL OFFER: Do not offer a call.")
    if prototype_url and prototype_url.strip():
        parts.append(
            f"PROTOTYPE: a working prototype for this job is live at {prototype_url.strip()}. "
            "Work it into the letter where it strengthens the case, with the URL written exactly."
        )
    if extra_points and extra_points.strip():
        parts.append(f"EXTRA POINTS FROM {name} (include these):\n{format_inclusions(extra_points)}")
    if brief.questions:
        numbered = "\n".join(f"{i}. {q.strip()}" for i, q in enumerate(brief.questions, 1))
        parts.append(f"SCREENING QUESTIONS (answer each, in order):\n{numbered}")
    else:
        parts.append("SCREENING QUESTIONS: none; return an empty screening_answers list.")
    if repair_notes:
        parts.append(
            "REPAIR: your previous draft broke these rules. Write a fresh draft that fixes every one:\n"
            + _bullets(repair_notes)
        )
    return "\n\n".join(parts)


def _align_answers(questions: list[str], raw: list[dict]) -> list[dict]:
    by_question = {str(a.get("question", "")).strip().lower(): str(a.get("answer", "")).strip() for a in raw}
    aligned = []
    for i, question in enumerate(questions):
        answer = by_question.get(question.strip().lower())
        if answer is None and i < len(raw):
            answer = str(raw[i].get("answer", "")).strip()
        aligned.append({"question": question, "answer": answer or ""})
    return aligned


async def write_application(
    profile,
    brief: JobBrief,
    evidence: Evidence,
    include_call_offer: bool,
    prototype_url: Optional[str],
    extra_points: Optional[str],
    repair_notes: Optional[list[str]] = None,
) -> Draft:
    """Write the cover letter and all screening answers in one call."""
    data = await structured_call(
        model=settings.cover_letter_model,
        system=[{"type": "text", "text": build_writer_system(profile), "cache_control": {"type": "ephemeral"}}],
        user=build_writer_user_prompt(
            profile, brief, evidence, include_call_offer, prototype_url, extra_points, repair_notes
        ),
        schema=WRITER_SCHEMA,
        effort=settings.writer_effort,
        max_tokens=16000,
    )
    letter = finalize_letter(data.get("cover_letter", ""), profile.preferred_closing)

    allowed = {str(fact.id) for fact in evidence.facts}
    fact_ids = [fid for fid in dict.fromkeys(data.get("fact_ids_used", [])) if fid in allowed]

    return Draft(
        cover_letter=letter,
        screening_answers=_align_answers(brief.questions, data.get("screening_answers", [])),
        fact_ids_used=fact_ids,
    )
```

- [ ] **Step 4: Run and confirm pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_writer.py
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add api/app/services/generation/writer.py api/tests/test_generation_writer.py && git commit -m "$(cat <<'EOF'
feat(generation): Opus 5.5 writer for letter + answers in one call

Principles-over-templates prompt: voice samples are the primary style
guide, specifics only from the evidence block, hard rules kept (no
sentence starts with "I", no salutation, banned phrases). Job-driven
length; call offer and prototype URL are woven in by the model.
System prompt is job-independent and sent as a cached block; closing
(Warm regards, + preferred_closing) is appended deterministically.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.7: Orchestrator — `generate_application` with one repair pass

**Files:**
- Create: `api/app/services/generation/orchestrator.py`
- Modify: `api/app/services/generation/__init__.py` (export)
- Create: `api/tests/test_generation_orchestrator.py`

**Interfaces:**
- Consumes: `build_job_brief`, `select_evidence`, `write_application`, `check_rules`, `check_claims`, `CLAIM_CHECK_SKIPPED`, and `credit_facts(db, fact_ids, won=False)` (Phase 1 Task 1.4).
- Produces: `@dataclass GenerationResult(draft: Draft, brief: JobBrief, evidence: Evidence, warnings: list[str])`; `async generate_application(db, user, profile, title, description, skills, questions, include_call_offer=True, prototype_url=None, extra_points=None, brief: JobBrief | None = None, credit_usage: bool = True) -> GenerationResult`; `from app.services.generation import generate_application`. The two trailing keyword arguments extend the shared contract: `brief` reuses a stored brief (Task 2.9, spec §2.3) and `credit_usage=False` keeps a discarded letter from inflating `times_used`.
- Behaviour: brief, then evidence, write and verify. A single repair write runs when any warning other than `CLAIM_CHECK_SKIPPED` exists. The facts in the final `fact_ids_used` get `times_used = times_used + 1` in the caller's transaction; the caller commits. If no facts were found, `NO_FACTS_WARNING` is appended.

- [ ] **Step 1: Write the failing tests.** Create `/Users/admin/dev2/UpApply/api/tests/test_generation_orchestrator.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_orchestrator.py
```

Expected: collection error `ImportError: cannot import name 'generate_application' from 'app.services.generation'`.

- [ ] **Step 3: Implement.** Create `/Users/admin/dev2/UpApply/api/app/services/generation/orchestrator.py`:

```python
"""Generation v2 pipeline: brief → evidence → write → verify → at most one repair."""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.facts import credit_facts
from app.services.generation.brief import JobBrief, build_job_brief
from app.services.generation.evidence import Evidence, select_evidence
from app.services.generation.verify import CLAIM_CHECK_SKIPPED, check_claims, check_rules
from app.services.generation.writer import Draft, write_application

NO_FACTS_WARNING = "No approved facts matched this job, so the draft has no verified specifics."


@dataclass
class GenerationResult:
    draft: Draft
    brief: JobBrief
    evidence: Evidence
    warnings: list[str]


async def _verify(
    draft: Draft, brief: JobBrief, evidence: Evidence, profile, prototype_url: Optional[str]
) -> list[str]:
    warnings = check_rules(draft.cover_letter, brief, profile.preferred_closing)
    if prototype_url and prototype_url.strip() and prototype_url.strip() not in draft.cover_letter:
        warnings.append(f"Prototype URL {prototype_url.strip()} is missing from the letter.")
    for item in draft.screening_answers:
        if not item.get("answer"):
            warnings.append(f'No answer for screening question: "{item.get("question", "")}"')
    warnings.extend(await check_claims(draft, evidence))
    return warnings


async def _credit_usage(db: AsyncSession, evidence: Evidence, draft: Draft) -> None:
    used = set(draft.fact_ids_used)
    ids = [fact.id for fact in evidence.facts if str(fact.id) in used]
    # Phase 1 Task 1.4: won=False increments times_used (flush-free UPDATE in the caller's transaction)
    await credit_facts(db, ids, won=False)


async def generate_application(
    db: AsyncSession,
    user,
    profile,
    title: str,
    description: str,
    skills: list[str],
    questions: list[str],
    include_call_offer: bool = True,
    prototype_url: Optional[str] = None,
    extra_points: Optional[str] = None,
    brief: Optional[JobBrief] = None,
    credit_usage: bool = True,
) -> GenerationResult:
    """Run the full v2 pipeline. The caller owns the transaction (commit).

    `brief`: a stored brief to reuse (per-question screening, spec §2.3) — skips the Haiku call.
    `credit_usage=False`: the letter will be discarded, so cited facts must not gain times_used
    (that would depress their win_signal in the rerank).
    """
    if brief is None:
        brief = await build_job_brief(title, description, skills, questions)
    evidence = await select_evidence(db, user.id, brief, profile.proposal_anchors)

    draft = await write_application(profile, brief, evidence, include_call_offer, prototype_url, extra_points)
    warnings = await _verify(draft, brief, evidence, profile, prototype_url)

    repairable = [w for w in warnings if w != CLAIM_CHECK_SKIPPED]
    if repairable:
        draft = await write_application(
            profile, brief, evidence, include_call_offer, prototype_url, extra_points,
            repair_notes=repairable,
        )
        warnings = await _verify(draft, brief, evidence, profile, prototype_url)

    if not evidence.facts:
        warnings.append(NO_FACTS_WARNING)

    if credit_usage:
        await _credit_usage(db, evidence, draft)
    return GenerationResult(draft=draft, brief=brief, evidence=evidence, warnings=warnings)
```

Replace the contents of `/Users/admin/dev2/UpApply/api/app/services/generation/__init__.py` with:

```python
"""Generation v2 engine: brief → evidence → write → verify (spec §2)."""
from app.services.generation.orchestrator import generate_application

__all__ = ["generate_application"]
```

- [ ] **Step 4: Run and confirm pass (whole generation package)**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_orchestrator.py tests/test_generation_brief.py tests/test_generation_evidence.py tests/test_generation_verify.py tests/test_generation_writer.py
```

Expected: all passed (7 in `test_generation_orchestrator.py`), 0 failed.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add api/app/services/generation/__init__.py api/app/services/generation/orchestrator.py api/tests/test_generation_orchestrator.py && git commit -m "$(cat <<'EOF'
feat(generation): generate_application orchestrator

brief -> evidence -> write -> verify with exactly one repair pass when
rules, prototype URL, empty answers or unsupported claims fail; a
verifier outage alone does not trigger repair. Increments times_used on
facts the final draft cites, inside the caller's transaction.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.8: Route `POST /jobs/cover-letters/generate` to v2 behind the flag

**Files:**
- Modify: `api/app/schemas/job.py:119-155` (`CoverLetterGenerateRequest`, `CoverLetterResponse`)
- Modify: `api/app/api/v1/jobs.py:44-48` (imports) and `generate_cover_letter_endpoint`, ~826-890: everything after `relevant_memories = ar.relevant_memories` through the `return CoverLetterResponse(...)`
- Create: `api/tests/test_generation_endpoints.py`

**Interfaces:**
- Consumes: `generate_application`, `GenerationResult`, `profile.generation_v2`, and the new `CoverLetter` columns.
- Produces: `CoverLetterGenerateRequest.screening_questions: Optional[List[str]] = None`; `CoverLetterResponse.screening_answers: Optional[List[dict]] = None`, `.verify_warnings: Optional[List[str]] = None`, `.facts_used: Optional[List[dict]] = None` (`{id, statement}` of cited facts). Every existing field is unchanged. When the flag is on, `model_used = settings.cover_letter_model` and `prompt_version = "v2"`.

- [ ] **Step 1: Write the failing tests.** Create `/Users/admin/dev2/UpApply/api/tests/test_generation_endpoints.py`:

```python
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
```

Also append these two tests to the same file:

```python


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
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_endpoints.py
```

Expected: 4 failed. The errors are `AttributeError: <module 'app.api.v1.jobs'> does not have the attribute 'generate_application'`.

- [ ] **Step 3a: Schemas.** In `/Users/admin/dev2/UpApply/api/app/schemas/job.py`, after `include_call_offer: bool = True  # Append no-cost/no-commitment call offer before close` (inside `CoverLetterGenerateRequest`) add:

```python
    screening_questions: Optional[List[str]] = None  # v2: answered jointly with the letter
```

In `CoverLetterResponse`, after `highlighted_skills: Optional[List[str]] = None` add:

```python

    # Generation v2 (None on the legacy path)
    screening_answers: Optional[List[dict]] = None
    verify_warnings: Optional[List[str]] = None
    facts_used: Optional[List[dict]] = None  # [{id, statement}] of facts the draft cites
```

- [ ] **Step 3b: Endpoint.** In `/Users/admin/dev2/UpApply/api/app/api/v1/jobs.py`, after the `from app.services.cover_letter import (...)` block add:

```python
from app.services.generation import generate_application
from app.services.llm import LLMError
```

Then replace this span inside `generate_cover_letter_endpoint`. It runs from `    # Find relevant past proposals to use as writing examples` through the closing `    )` of `return CoverLetterResponse(...)`. Phase 0 and Task 2.1 left `model_used=settings.legacy_cover_letter_model,` in the `CoverLetter(...)` call. Replace it with:

```python
    v2_result = None
    if profile.generation_v2:
        try:
            v2_result = await generate_application(
                db=db,
                user=current_user,
                profile=profile,
                title=job_title,
                description=job_description,
                skills=job_skills,
                questions=body.screening_questions or [],
                include_call_offer=body.include_call_offer,
                prototype_url=body.prototype_url,
                extra_points=body.custom_instructions,
            )
        except LLMError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Draft generation failed upstream: {exc}",
            )
        content = v2_result.draft.cover_letter
    else:
        # Find relevant past proposals to use as writing examples
        past_proposals = await find_relevant_proposals(
            db=db,
            user_id=current_user.id,
            job_description=job_description,
            job_skills=job_skills,
            limit=3,  # Top 3 most similar past proposals
            successful_only=False,  # Include all, but successful ones are prioritized
        )

        # Generate cover letter
        content = await generate_cover_letter(
            job_title=job_title,
            job_description=job_description,
            job_skills=job_skills,
            budget=budget,
            skill_matches=skill_matches,
            missing_skills=missing_skills,
            relevant_memories=relevant_memories,
            profile=profile,
            past_proposals=past_proposals,
            inclusions=body.custom_instructions,
            prototype_url=body.prototype_url,
            include_call_offer=body.include_call_offer,
        )

    # Save cover letter
    cover_letter = CoverLetter(
        user_id=current_user.id,
        job_id=job_id,
        content=content,
        model_used=settings.cover_letter_model if v2_result else settings.legacy_cover_letter_model,
        memories_used=None if v2_result else [m["id"] for m in relevant_memories],
        version=1,
    )
    v2_fields: dict = {}
    if v2_result:
        cover_letter.prompt_version = "v2"
        cover_letter.word_count = len(content.split())
        cover_letter.brief = v2_result.brief.model_dump()
        cover_letter.fact_ids_used = v2_result.draft.fact_ids_used
        cover_letter.voice_sample_ids = [str(p.id) for p in v2_result.evidence.voice_samples]
        cover_letter.verify_warnings = v2_result.warnings
        cited = set(v2_result.draft.fact_ids_used)
        v2_fields = {
            "screening_answers": v2_result.draft.screening_answers,
            "verify_warnings": v2_result.warnings,
            "facts_used": [
                {"id": str(f.id), "statement": f.statement}
                for f in v2_result.evidence.facts
                if str(f.id) in cited
            ],
        }
    db.add(cover_letter)
    await db.commit()
    await db.refresh(cover_letter)

    # Get match score
    match_score = None
    if body.job_id:
        result = await db.execute(
            select(Job).where(Job.id == job_id)
        )
        job_record = result.scalar_one_or_none()
        if job_record:
            match_score = job_record.match_score

    return CoverLetterResponse(
        id=cover_letter.id,
        user_id=cover_letter.user_id,
        job_id=cover_letter.job_id,
        content=cover_letter.content,
        model_used=cover_letter.model_used,
        memories_used=cover_letter.memories_used,
        word_count=len(content.split()),
        version=cover_letter.version,
        is_final=False,
        created_at=cover_letter.created_at,
        match_score=match_score,
        highlighted_skills=[m.skill for m in skill_matches if m.match_type == "exact"],
        **v2_fields,
    )
```

- [ ] **Step 4: Run and confirm pass (plus the Phase 0 regression for this endpoint)**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_endpoints.py tests/test_cover_letter_model_used.py
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add api/app/schemas/job.py api/app/api/v1/jobs.py api/tests/test_generation_endpoints.py && git commit -m "$(cat <<'EOF'
feat(api): route cover letter generation to v2 when generation_v2 is on

Flag on: generate_application writes letter + screening answers; the
brief, cited fact ids, voice sample ids and verify warnings are stored
on the cover letter. Response adds optional screening_answers,
verify_warnings and facts_used. Flag off: legacy path unchanged.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.9: Route `POST /screening-answers/generate` to v2 behind the flag

**Files:**
- Modify: `api/app/api/v1/screening_answers.py:1-37` (imports, request and response models) and `generate_screening_answer`, right after `profile = profile_result.scalar_one_or_none()` (~line 254)
- Modify: `api/tests/test_generation_endpoints.py` (append)
- Modify: `extension/src/lib/api-client.ts:345-350` (`generateScreeningAnswer` gains `coverLetterId`)
- Modify: `extension/src/sidebar/pages/Generator.tsx` (`handleGenerateAnswer`, ~line 299)

**Interfaces:**
- Consumes: `generate_application` (with `questions=[body.question]`, `brief=`, `credit_usage=False`, Task 2.7); `CoverLetter.brief` (Task 2.2); `JobBrief.model_validate`.
- Produces: `ScreeningAnswerGenerateRequest.cover_letter_id: Optional[str] = None`; `ScreeningAnswerGenerateResponse(answer: str, verify_warnings: Optional[List[str]] = None)`; `apiClient.generateScreeningAnswer(question, jobTitle?, jobDescription?, jobSkills?, coverLetterId?)`. The legacy branch is unchanged and includes the Phase 0 `body.` fix.
- Spec §2.3 brief reuse: when `cover_letter_id` names one of the user's letters that has a stored `brief`, that brief is reused with `questions=[body.question]`, so the Haiku brief call is skipped and the answer is written against the same needs as the letter. Without it (no draft yet, or a legacy letter) a fresh brief is built.
- The per-question button still runs the writer, which also writes a letter that is discarded (about $0.09 per click on Opus 5.5). `credit_usage=False` keeps that discarded letter from adding to `times_used`. The usual flow, "Generate all", gets answers from the letter call (Task 2.10) and makes no extra calls.

- [ ] **Step 1: Write the failing tests.** Append to `/Users/admin/dev2/UpApply/api/tests/test_generation_endpoints.py`:

```python


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
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_endpoints.py -k screening
```

Expected: 3 failed. The errors are `AttributeError: <module 'app.api.v1.screening_answers'> does not have the attribute 'generate_application'`.

- [ ] **Step 3: Implement.** In `/Users/admin/dev2/UpApply/api/app/api/v1/screening_answers.py`, after `from app.models.screening_answer import ScreeningAnswer` add:

```python
from app.models.cover_letter import CoverLetter
from app.services.generation import generate_application
from app.services.generation.brief import JobBrief
from app.services.llm import LLMError
```

Replace:

```python
class ScreeningAnswerGenerateRequest(BaseModel):
    question: str
    job_title: Optional[str] = None
    job_description: Optional[str] = None
    job_skills: Optional[List[str]] = None


class ScreeningAnswerGenerateResponse(BaseModel):
    answer: str
```

with:

```python
class ScreeningAnswerGenerateRequest(BaseModel):
    question: str
    job_title: Optional[str] = None
    job_description: Optional[str] = None
    job_skills: Optional[List[str]] = None
    cover_letter_id: Optional[str] = None  # v2: reuse this letter's stored brief (spec §2.3)


class ScreeningAnswerGenerateResponse(BaseModel):
    answer: str
    verify_warnings: Optional[List[str]] = None
```

Inside `generate_screening_answer`, immediately after `    profile = profile_result.scalar_one_or_none()`, insert:

```python

    if profile and profile.generation_v2:
        cached_brief = None
        title = body.job_title or ""
        description = body.job_description or ""
        if body.cover_letter_id:
            letter = (await db.execute(
                select(CoverLetter).where(
                    CoverLetter.id == body.cover_letter_id,
                    CoverLetter.user_id == current_user.id,
                )
            )).scalar_one_or_none()
            if letter is not None and letter.brief:
                cached_brief = JobBrief.model_validate({**letter.brief, "questions": [body.question]})
                title = title or cached_brief.title
                description = description or cached_brief.description
        try:
            result = await generate_application(
                db=db,
                user=current_user,
                profile=profile,
                title=title,
                description=description,
                skills=body.job_skills or [],
                questions=[body.question],
                brief=cached_brief,
                credit_usage=False,  # the letter written alongside this answer is discarded
            )
        except LLMError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Answer generation failed upstream: {exc}",
            )
        answers = result.draft.screening_answers
        return ScreeningAnswerGenerateResponse(
            answer=answers[0]["answer"] if answers else "",
            verify_warnings=result.warnings,
        )
```

(`select` is already imported in this module.)

- [ ] **Step 3b: Extension pass-through.** In `/Users/admin/dev2/UpApply/extension/src/lib/api-client.ts` replace:

```ts
  async generateScreeningAnswer(question: string, jobTitle?: string, jobDescription?: string, jobSkills?: string[]) {
    return this.request<{ answer: string }>('/api/v1/screening-answers/generate', {
      method: 'POST',
      body: { question, job_title: jobTitle, job_description: jobDescription, job_skills: jobSkills },
    });
  }
```

with:

```ts
  async generateScreeningAnswer(question: string, jobTitle?: string, jobDescription?: string, jobSkills?: string[], coverLetterId?: string) {
    return this.request<{ answer: string; verify_warnings?: string[] | null }>('/api/v1/screening-answers/generate', {
      method: 'POST',
      body: { question, job_title: jobTitle, job_description: jobDescription, job_skills: jobSkills, cover_letter_id: coverLetterId },
    });
  }
```

In `/Users/admin/dev2/UpApply/extension/src/sidebar/pages/Generator.tsx`, inside `handleGenerateAnswer`, replace:

```tsx
        currentJob?.skills ?? undefined,
      );
      setQuestionAnswers(prev => ({ ...prev, [key]: result.answer }));
```

with:

```tsx
        currentJob?.skills ?? undefined,
        useAppStore.getState().coverLetterId ?? undefined,
      );
      setQuestionAnswers(prev => ({ ...prev, [key]: result.answer }));
```

- [ ] **Step 4: Run and confirm pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_generation_endpoints.py tests/test_screening_generate.py
cd /Users/admin/dev2/UpApply/extension && npm run type-check
```

Expected: all passed (7 in `test_generation_endpoints.py`), 0 failed; `tsc --noEmit` exits 0.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add api/app/api/v1/screening_answers.py api/tests/test_generation_endpoints.py extension/src/lib/api-client.ts extension/src/sidebar/pages/Generator.tsx && git commit -m "$(cat <<'EOF'
feat(api): route screening answer generation to v2 when flag is on

Same engine, evidence and model as the letter (no more memory-blind
gpt-4.1-nano answers for v2 users). Reuses the letter's stored brief
when cover_letter_id is sent, and never credits times_used for the
discarded letter. Response adds optional verify_warnings. Legacy path
unchanged when the flag is off.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.10: Extension — send questions, show warnings and facts under the draft

**Files:**
- Modify: `extension/src/lib/api-client.ts:883-903` (`CoverLetterGenerateRequest`, `CoverLetter`)
- Modify: `extension/src/sidebar/store.ts`: lines 14-35 (`AppState`), 83-92 (initial state), 104-111 (`setCurrentJob` reset), 192-199 (logout reset), 281-299 (`generateCoverLetter`), 320-324 (`regenerateCoverLetter`)
- Modify: `extension/src/sidebar/pages/Generator.tsx`: lines 15-20 (store destructure), 324-326 (`handleGenerateAll`), 518-519 (panel props)
- Modify: `extension/src/sidebar/components/generator/CoverLetterPanel.tsx`: lines 23 and 60 (props), 115-117 (render)

**Interfaces:**
- Consumes: `CoverLetterResponse.screening_answers | verify_warnings | facts_used` (Task 2.8).
- Produces: `export interface DraftMeta { warnings: string[]; factsUsed: { id: string; statement: string }[]; screeningAnswers: { question: string; answer: string }[] }` and store field `draftMeta: DraftMeta | null`; `CoverLetterPanel` props `verifyWarnings: string[]`, `factsUsed: { id: string; statement: string }[]`.

No extension test runner exists yet; `npm run type-check` is the test here.

- [ ] **Step 1: Write the consuming code first (it must fail type-check).** In `/Users/admin/dev2/UpApply/extension/src/sidebar/pages/Generator.tsx` replace:

```tsx
    coverLetterError,
    savedJobId,
```

with:

```tsx
    coverLetterError,
    draftMeta,
    savedJobId,
```

Replace:

```tsx
              applicationId={applicationId}
              onGenerate={handleGenerate}
```

with:

```tsx
              applicationId={applicationId}
              verifyWarnings={draftMeta?.warnings ?? []}
              factsUsed={draftMeta?.factsUsed ?? []}
              onGenerate={handleGenerate}
```

Replace:

```tsx
  const handleGenerateAll = async () => {
    await generateCoverLetter(inclusions.trim() || undefined, prototypeUrl.trim() || undefined, includeCallOffer);
    if (currentJob?.screeningQuestions && currentJob.screeningQuestions.length > 0) {
```

with:

```tsx
  const handleGenerateAll = async () => {
    await generateCoverLetter(inclusions.trim() || undefined, prototypeUrl.trim() || undefined, includeCallOffer);
    // v2 answers come back with the letter (same evidence, one call) — use them instead of per-question calls
    const v2Answers = useAppStore.getState().draftMeta?.screeningAnswers ?? [];
    if (v2Answers.length > 0 && currentJob?.screeningQuestions) {
      const fromDraft: Record<string, string> = {};
      currentJob.screeningQuestions.forEach((q, i) => {
        const match = v2Answers.find(a => a.question === q.question) ?? v2Answers[i];
        if (match?.answer) fromDraft[`q${i}`] = match.answer;
      });
      setQuestionAnswers(prev => ({ ...prev, ...fromDraft }));
      return;
    }
    if (currentJob?.screeningQuestions && currentJob.screeningQuestions.length > 0) {
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/extension && npm run type-check
```

Expected: FAIL. `tsc` reports `Property 'draftMeta' does not exist on type 'AppState'` and `Property 'verifyWarnings' does not exist on type 'IntrinsicAttributes & CoverLetterPanelProps'`.

- [ ] **Step 3a: API types.** In `/Users/admin/dev2/UpApply/extension/src/lib/api-client.ts` replace:

```ts
  prototype_url?: string;
  include_call_offer?: boolean;
}
```

with:

```ts
  prototype_url?: string;
  include_call_offer?: boolean;
  screening_questions?: string[];
}
```

and in `export interface CoverLetter` replace:

```ts
  highlighted_skills?: string[];
  created_at: string;
}
```

with:

```ts
  highlighted_skills?: string[];
  created_at: string;
  // Generation v2 (null on the legacy path)
  screening_answers?: { question: string; answer: string }[] | null;
  verify_warnings?: string[] | null;
  facts_used?: { id: string; statement: string }[] | null;
}
```

- [ ] **Step 3b: Store.** In `/Users/admin/dev2/UpApply/extension/src/sidebar/store.ts` insert before `interface AppState {`:

```ts
export interface DraftMeta {
  warnings: string[];
  factsUsed: { id: string; statement: string }[];
  screeningAnswers: { question: string; answer: string }[];
}

```

In `AppState`, replace:

```ts
  coverLetterError: string | null;

  // Job tracking
```

with:

```ts
  coverLetterError: string | null;
  // Generation v2 extras for the current draft (null on the legacy path)
  draftMeta: DraftMeta | null;

  // Job tracking
```

Initial state: replace

```ts
  coverLetterError: null,
  savedJobId: null,
  applicationId: null,
  currentView: 'auth',
```

with:

```ts
  coverLetterError: null,
  draftMeta: null,
  savedJobId: null,
  applicationId: null,
  currentView: 'auth',
```

`setCurrentJob` reset: replace

```ts
        coverLetterError: null,
      });
    } else {
```

with:

```ts
        coverLetterError: null,
        draftMeta: null,
      });
    } else {
```

Logout reset: replace

```ts
      coverLetterError: null,
      currentView: 'auth',
```

with:

```ts
      coverLetterError: null,
      draftMeta: null,
      currentView: 'auth',
```

In `generateCoverLetter`, replace:

```ts
        include_call_offer: includeCallOffer,
      });
      set({
        coverLetter: result.content,
        coverLetterId: result.id,
        savedJobId: result.job_id,
        coverLetterLoading: false,
      });
```

with:

```ts
        include_call_offer: includeCallOffer,
        screening_questions: currentJob.screeningQuestions?.map((q) => q.question),
      });
      set({
        coverLetter: result.content,
        coverLetterId: result.id,
        savedJobId: result.job_id,
        coverLetterLoading: false,
        draftMeta:
          result.verify_warnings || result.facts_used || result.screening_answers
            ? {
                warnings: result.verify_warnings ?? [],
                factsUsed: result.facts_used ?? [],
                screeningAnswers: result.screening_answers ?? [],
              }
            : null,
      });
```

In `regenerateCoverLetter` (legacy endpoint, no v2 metadata), replace:

```ts
        coverLetterId: result.id,
        coverLetterLoading: false,
      });
    } catch (error) {
      console.error('Regeneration error:', error);
```

with:

```ts
        coverLetterId: result.id,
        coverLetterLoading: false,
        draftMeta: null,
      });
    } catch (error) {
      console.error('Regeneration error:', error);
```

- [ ] **Step 3c: Panel.** In `/Users/admin/dev2/UpApply/extension/src/sidebar/components/generator/CoverLetterPanel.tsx` replace:

```tsx
  applicationId: string | null;
  onGenerate: () => void;
```

with:

```tsx
  applicationId: string | null;
  verifyWarnings: string[];
  factsUsed: { id: string; statement: string }[];
  onGenerate: () => void;
```

replace:

```tsx
  applicationId,
  onGenerate,
```

with:

```tsx
  applicationId,
  verifyWarnings,
  factsUsed,
  onGenerate,
```

and replace:

```tsx
            {coverLetter}
          </div>

          <button type="button" onClick={onFill} className="btn-primary w-full mt-3">
```

with:

```tsx
            {coverLetter}
          </div>

          {verifyWarnings.length > 0 && (
            <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
              <p className="font-medium mb-1">Check before sending</p>
              <ul className="list-disc pl-4 space-y-0.5">
                {verifyWarnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {factsUsed.length > 0 && (
            <details className="mt-2 text-xs text-gray-600">
              <summary className="cursor-pointer select-none">Facts used ({factsUsed.length})</summary>
              <ul className="list-disc pl-4 mt-1 space-y-0.5">
                {factsUsed.map((f) => (
                  <li key={f.id}>{f.statement}</li>
                ))}
              </ul>
            </details>
          )}

          <button type="button" onClick={onFill} className="btn-primary w-full mt-3">
```

- [ ] **Step 4: Run and confirm pass**

```bash
cd /Users/admin/dev2/UpApply/extension && npm run type-check
```

Expected: exits 0 with no errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add extension/src/lib/api-client.ts extension/src/sidebar/store.ts extension/src/sidebar/pages/Generator.tsx extension/src/sidebar/components/generator/CoverLetterPanel.tsx && git commit -m "$(cat <<'EOF'
feat(extension): show v2 verify warnings and cited facts under the draft

Generate sends the page's screening questions; v2 responses populate
draftMeta (warnings, facts used, screening answers). Generate-all uses
the jointly written answers instead of per-question calls. Legacy
responses leave draftMeta null, so the UI is unchanged for flag-off users.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.11: Golden-set blind A/B harness (`scripts/eval_generation.py`)

**Files:**
- Create: `scripts/eval_generation.py`
- Create: `api/tests/test_eval_generation.py`

**Interfaces:**
- Consumes: the golden JSON, a list of `{"id", "title", "description", "skills"?: [], "questions"?: [], "chris_letter", "outcome"?}`. Chris assembles it from proposal-detail scrapes and weights it toward replies. Also consumes `run_full_analysis`, `find_relevant_proposals`, and `generate_cover_letter` (legacy), plus `generate_application` (v2), via `app.core.database.async_session_maker`.
- Produces: `assign_sides(job_ids, seed) -> dict[str, dict[str, str]]`, `render_pairs_markdown(jobs, outputs, sides) -> str`, `write_score_sheet(path, job_ids)`, `score(rows, key) -> dict`. CLI `generate` writes `docs/evals/<date>/pairs.md`, `scores.csv` and `key.json`; CLI `score` prints the pass/fail summary for spec §4.2: new preferred in ≥75% of pairs with ties counting against new, zero `Unsupported claim` warnings, and ≥2 cited facts per draft.
- Each job runs in its own session that is never committed. The eval therefore never credits `times_used` or persists jobs.

- [ ] **Step 1: Write the failing tests.** Create `/Users/admin/dev2/UpApply/api/tests/test_eval_generation.py`:

```python
"""Golden-set eval harness: blind pairing and scoring (pure functions)."""
import csv
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval_generation.py"
spec = importlib.util.spec_from_file_location("eval_generation", SCRIPT)
eval_generation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_generation)


def test_assign_sides_is_deterministic_and_randomised():
    ids = [f"job{i}" for i in range(20)]
    first = eval_generation.assign_sides(ids, seed=7)
    assert first == eval_generation.assign_sides(ids, seed=7)
    assert {s["A"] for s in first.values()} == {"new", "old"}
    for s in first.values():
        assert {s["A"], s["B"]} == {"new", "old"}


def test_render_pairs_is_blind():
    jobs = [{"id": "j1", "title": "Azure move", "description": "Post text", "chris_letter": "Chris text"}]
    outputs = {"j1": {"old": "OLD LETTER", "new": "NEW LETTER"}}
    md = eval_generation.render_pairs_markdown(jobs, outputs, {"j1": {"A": "new", "B": "old"}})
    assert md.index("NEW LETTER") < md.index("OLD LETTER")
    assert "Chris text" in md and "Post text" in md
    lowered = md.lower()
    for leak in ("legacy", "v2", "old letter (", "new letter ("):
        assert leak not in lowered


def test_write_score_sheet(tmp_path):
    path = tmp_path / "scores.csv"
    eval_generation.write_score_sheet(path, ["j1", "j2"])
    rows = list(csv.DictReader(path.open()))
    assert [r["job_id"] for r in rows] == ["j1", "j2"]
    assert rows[0]["preferred"] == ""


def _key(new_meta):
    return {
        "sides": {"j1": {"A": "new", "B": "old"}, "j2": {"A": "old", "B": "new"},
                  "j3": {"A": "new", "B": "old"}, "j4": {"A": "old", "B": "new"}},
        "new_meta": new_meta,
    }


GOOD_META = {j: {"warnings": [], "fact_ids_used": ["a", "b"]} for j in ("j1", "j2", "j3", "j4")}


def test_score_passes_at_75_percent_with_clean_drafts():
    rows = [{"job_id": "j1", "preferred": "A"}, {"job_id": "j2", "preferred": "b"},
            {"job_id": "j3", "preferred": "A"}, {"job_id": "j4", "preferred": "A"}]
    result = eval_generation.score(rows, _key(GOOD_META))
    assert result["judged"] == 4
    assert result["new_preferred"] == 3
    assert result["preference"] == 0.75
    assert result["passed"] is True


def test_score_ties_count_against_new_and_blank_rows_are_ignored():
    rows = [{"job_id": "j1", "preferred": "A"}, {"job_id": "j2", "preferred": "tie"},
            {"job_id": "j3", "preferred": ""}, {"job_id": "j4", "preferred": "B"}]
    result = eval_generation.score(rows, _key(GOOD_META))
    assert result["judged"] == 3
    assert result["new_preferred"] == 2
    assert result["passed"] is False


def test_score_fails_on_unsupported_claims_or_thin_drafts():
    meta = dict(GOOD_META)
    meta["j1"] = {"warnings": ["Unsupported claim: $2M (no fact)"], "fact_ids_used": ["a"]}
    rows = [{"job_id": j, "preferred": s} for j, s in (("j1", "A"), ("j2", "B"), ("j3", "A"), ("j4", "B"))]
    result = eval_generation.score(rows, _key(meta))
    assert result["preference"] == 1.0
    assert result["unsupported_claims"] == 1
    assert result["drafts_under_2_facts"] == ["j1"]
    assert result["passed"] is False
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_eval_generation.py
```

Expected: collection error `FileNotFoundError: [Errno 2] No such file or directory: '/Users/admin/dev2/UpApply/scripts/eval_generation.py'`.

- [ ] **Step 3: Implement.** Create `/Users/admin/dev2/UpApply/scripts/eval_generation.py`:

```python
#!/usr/bin/env python3
"""Golden-set blind A/B evaluation: legacy generator vs generation v2 (spec §4.2).

Golden JSON (list of jobs where Chris's real submitted letter is known):
    [{"id": "p-123", "title": "...", "description": "...", "skills": ["..."],
      "questions": ["..."], "chris_letter": "...", "outcome": "replied"}]

Generate the blind packet (needs DATABASE_URL, OPENAI_API_KEY, ANTHROPIC_API_KEY):
    cd api && doppler run --project upapply --config prd -- \\
        ./venv/bin/python ../scripts/eval_generation.py generate \\
        --email chris@servicevision.net --golden ../docs/evals/golden.json

Then fill in docs/evals/<date>/scores.csv (preferred = A, B or tie) without opening
key.json, and score it:
    ./venv/bin/python ../scripts/eval_generation.py score --run-dir ../docs/evals/<date>

Nothing is committed to the database: each job runs in its own session that is
closed without commit, so times_used and job rows are never persisted.
"""
import argparse
import asyncio
import csv
import json
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

PASS_PREFERENCE = 0.75
MIN_FACTS_CITED = 2


def assign_sides(job_ids: list[str], seed: int) -> dict[str, dict[str, str]]:
    """Randomly place the new letter on side A or B for each job (reproducible by seed)."""
    rng = random.Random(seed)
    sides = {}
    for job_id in job_ids:
        new_is_a = rng.random() < 0.5
        sides[job_id] = {"A": "new" if new_is_a else "old", "B": "old" if new_is_a else "new"}
    return sides


def render_pairs_markdown(jobs: list[dict], outputs: dict, sides: dict) -> str:
    lines = [
        "# Cover letter eval: blind pairs",
        "",
        "For each job, read the post and the letter that was actually sent, then letters A and B.",
        "Record the better letter in scores.csv as A, B or tie. Do not open key.json until scored.",
        "",
    ]
    for job in jobs:
        job_id = job["id"]
        letter = {side: outputs[job_id][which] for side, which in sides[job_id].items()}
        lines += [
            f"## {job_id}: {job['title']}",
            "",
            "### Job post",
            "",
            job["description"].strip(),
            "",
            "### Letter actually sent (reference)",
            "",
            (job.get("chris_letter") or "").strip() or "_not available_",
            "",
            "### Letter A",
            "",
            letter["A"].strip(),
            "",
            "### Letter B",
            "",
            letter["B"].strip(),
            "",
        ]
    return "\n".join(lines)


def write_score_sheet(path, job_ids: list[str]) -> None:
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["job_id", "preferred", "notes"])
        for job_id in job_ids:
            writer.writerow([job_id, "", ""])


def score(rows: list[dict], key: dict) -> dict:
    """Spec §4.2 pass bar: new preferred in >=75% of judged pairs (ties count against),
    zero unsupported claims, every new draft cites >=2 facts."""
    sides, new_meta = key["sides"], key["new_meta"]
    judged = [r for r in rows if r["preferred"].strip().upper() in ("A", "B", "TIE")]
    new_wins = sum(
        1
        for r in judged
        if r["preferred"].strip().upper() != "TIE"
        and sides[r["job_id"]][r["preferred"].strip().upper()] == "new"
    )
    preference = new_wins / len(judged) if judged else 0.0
    unsupported = sum(
        sum(1 for w in meta["warnings"] if w.startswith("Unsupported claim")) for meta in new_meta.values()
    )
    thin = sorted(job_id for job_id, meta in new_meta.items() if len(meta["fact_ids_used"]) < MIN_FACTS_CITED)
    return {
        "judged": len(judged),
        "new_preferred": new_wins,
        "preference": round(preference, 3),
        "unsupported_claims": unsupported,
        "drafts_under_2_facts": thin,
        "passed": bool(judged) and preference >= PASS_PREFERENCE and unsupported == 0 and not thin,
    }


async def _generate_one(email: str, job: dict) -> tuple[str, object]:
    from sqlalchemy import select

    from app.core.database import async_session_maker
    from app.models.user import User, UserProfile
    from app.services.cover_letter import generate_cover_letter
    from app.services.generation import generate_application
    from app.services.job_analysis import find_relevant_proposals, run_full_analysis

    skills = job.get("skills") or []
    async with async_session_maker() as db:  # closed without commit: nothing persists
        user = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one()
        profile = (await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))).scalar_one()
        analysis = await run_full_analysis(
            db=db, user_id=user.id, profile=profile, job_description=job["description"],
            job_skills=skills, job_title=job["title"],
        )
        past = await find_relevant_proposals(
            db=db, user_id=user.id, job_description=job["description"], job_skills=skills,
            limit=3, successful_only=False,
        )
        old = await generate_cover_letter(
            job_title=job["title"], job_description=job["description"], job_skills=skills, budget=None,
            skill_matches=analysis.skill_matches, missing_skills=analysis.missing_skills,
            relevant_memories=analysis.relevant_memories, profile=profile, past_proposals=past,
        )
        new = await generate_application(
            db=db, user=user, profile=profile, title=job["title"], description=job["description"],
            skills=skills, questions=job.get("questions") or [],
        )
        await db.rollback()
    return old, new


async def generate(email: str, golden: Path, out_dir: Path, seed: int) -> None:
    jobs = json.loads(golden.read_text())
    outputs, new_meta = {}, {}
    for job in jobs:
        old, new = await _generate_one(email, job)
        outputs[job["id"]] = {"old": old, "new": new.draft.cover_letter}
        new_meta[job["id"]] = {
            "warnings": new.warnings,
            "fact_ids_used": new.draft.fact_ids_used,
            "screening_answers": new.draft.screening_answers,
        }
        print(f"generated {job['id']} ({len(new.draft.fact_ids_used)} facts, {len(new.warnings)} warnings)")

    job_ids = [job["id"] for job in jobs]
    sides = assign_sides(job_ids, seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pairs.md").write_text(render_pairs_markdown(jobs, outputs, sides))
    write_score_sheet(out_dir / "scores.csv", job_ids)
    (out_dir / "key.json").write_text(
        json.dumps({"seed": seed, "sides": sides, "new_meta": new_meta, "outputs": outputs}, indent=2)
    )
    print(f"wrote {out_dir}/pairs.md, scores.csv, key.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--email", required=True)
    gen.add_argument("--golden", required=True, type=Path)
    gen.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "evals" / date.today().isoformat())
    gen.add_argument("--seed", type=int, default=20261012)
    sc = sub.add_parser("score")
    sc.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()

    if args.command == "generate":
        asyncio.run(generate(args.email, args.golden, args.out_dir, args.seed))
    else:
        rows = list(csv.DictReader((args.run_dir / "scores.csv").open()))
        key = json.loads((args.run_dir / "key.json").read_text())
        print(json.dumps(score(rows, key), indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run and confirm pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_eval_generation.py && ./venv/bin/python ../scripts/eval_generation.py --help
```

Expected: `6 passed`, then the usage text listing `{generate,score}`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply && git add scripts/eval_generation.py api/tests/test_eval_generation.py && git commit -m "$(cat <<'EOF'
feat(eval): golden-set blind A/B harness for generation v2

generate: runs legacy and v2 on each golden job (no DB commits), writes
docs/evals/<date>/pairs.md with sides randomised, a scores.csv sheet
and key.json. score: applies the spec 4.2 bar (>=75% new preferred,
ties count against; zero unsupported claims; >=2 cited facts each).

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Phase 2 exit criteria

```bash
# Full API suite: Phase 0+1 baseline plus the 57 Phase 2 tests, 0 failures
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q
# Import smoke test
cd /Users/admin/dev2/UpApply/api && ./venv/bin/python -c "from app.main import app; from app.services.generation import generate_application; print('OK')"
# Opus 5.5 constraints: nothing in the v2 package sends temperature/thinking/tool_choice (must print nothing)
cd /Users/admin/dev2/UpApply/api && grep -rnE "temperature=|thinking=|tool_choice=" app/services/llm.py app/services/generation/
# Migration chain up/down/up on a scratch DB ends at head 023
PGPASSWORD=upapply psql -h localhost -p 55499 -U upapply -d postgres -c "DROP DATABASE IF EXISTS upapply_mig_p2" -c "CREATE DATABASE upapply_mig_p2" && PGPASSWORD=upapply psql -h localhost -p 55499 -U upapply -d upapply_mig_p2 -c "CREATE EXTENSION IF NOT EXISTS vector" && cd /Users/admin/dev2/UpApply/api && DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_mig_p2 sh -c './venv/bin/alembic upgrade head && ./venv/bin/alembic downgrade -1 && ./venv/bin/alembic upgrade head && ./venv/bin/alembic current'
# Extension type-check
cd /Users/admin/dev2/UpApply/extension && npm run type-check
# Eval harness CLI loads
cd /Users/admin/dev2/UpApply/api && ./venv/bin/python ../scripts/eval_generation.py --help
# Branch contains exactly the 11 phase-2 commits on top of phase 1
cd /Users/admin/dev2/UpApply && git log --oneline feat/mdg-1-knowledge..feat/mdg-2-engine | wc -l
```

---

## Phase 3: Refine + learn loop

Phase 3 implements spec §3. The first draft from Phase 2 gets a small refine chat. Each turn re-sends the stored brief, evidence, voice samples, current draft and thread history to `claude-opus-5-5`. The model has one tool, `search_facts`, so "mention the Azure work" pulls a real approved fact instead of inventing one, and verify runs on every revised draft. Whatever Chris actually submits on Upwork is captured when he clicks Submit and sent to `PUT /jobs/cover-letters/{id}/final`. That call stores the final text, the answers and the edit distance, writes a voice sample (`author = chris_edited_ai`, or `chris` when he rewrote at least 90% of the draft) and pulls fact candidates out of his own words. Opening Upwork's Proposals page posts the visible statuses to `POST /proposals/outcomes`. That endpoint sets `proposals.outcome`, marks proposals with no reply after 14 days as `no_response`, and the first time a proposal reaches `replied`, `interviewed` or `hired` it adds one to `times_in_won` on each fact the submitted letter used. This replaces the broken `learning_engine.winning_proposal_to_memory` path. The extension also gets its first test runner (Vitest + jsdom), used only for the pure submit-capture field reader.

**Branch:** `feat/mdg-3-loop`, cut from `feat/mdg-2-engine` (stacked on Phase 2).

**Preconditions (from Phases 1–2, per the shared contract):**
- `app/models/fact.py` `Fact`, `app/schemas/fact.py` `FactCandidate`, `app/services/facts.py` (`search_facts`, `upsert_candidate`, `credit_facts`), `app/services/fact_extraction.py` `extract_facts`, `app/services/llm.py` `get_anthropic_client`.
- `proposals.author`, `proposals.outcome`, `proposals.job_needs_embedding` and `proposals.job_text` exist on the `Proposal` model.
- `cover_letters.brief`, `cover_letters.fact_ids_used`, `cover_letters.voice_sample_ids` and `cover_letters.verify_warnings` exist on the `CoverLetter` model (migration `023_generation_v2`).
- `app/services/generation/{brief,evidence,writer,verify}.py` export `JobBrief`, `Evidence`, `Draft`, `check_rules` and `check_claims`.
- `settings.cover_letter_model == "claude-opus-5-5"` and `settings.writer_effort == "high"`.
- `tests/conftest.py` TRUNCATE list includes `facts`.
- The working tree is clean. The version bump already sitting uncommitted in `extension/package.json`, `extension/package-lock.json` and `extension/public/manifest.json` predates this work, and Chris commits or stashes it before Phase 3 starts.

```bash
cd /Users/admin/dev2/UpApply
git checkout feat/mdg-2-engine && git pull --ff-only || true
git checkout -b feat/mdg-3-loop
```

---

### Task 3.1: Migration 024 and the `CoverLetter` refine/final columns

**Files:**
- Create: `/Users/admin/dev2/UpApply/api/alembic/versions/024_refine_loop.py`
- Modify: `/Users/admin/dev2/UpApply/api/app/models/cover_letter.py` (line 6 imports; insert above `created_at`, currently line 64)
- Create: `/Users/admin/dev2/UpApply/api/tests/test_migration_024.py`

**Interfaces:**
- Consumes: `down_revision = '023_generation_v2'` (Phase 2's migration revision id).
- Produces: columns `cover_letters.refine_messages JSONB NULL`, `final_text TEXT NULL`, `final_answers JSONB NULL`, `edit_distance_pct FLOAT NULL`; ORM attributes `CoverLetter.refine_messages: Optional[list]`, `final_text: Optional[str]`, `final_answers: Optional[list]`, `edit_distance_pct: Optional[float]`.

- [ ] **Step 1: Write the failing test** `/Users/admin/dev2/UpApply/api/tests/test_migration_024.py`

```python
"""Migration 024 (refine + learn loop) and CoverLetter ORM columns."""
import importlib.util
import pathlib
from unittest.mock import MagicMock

from app.models.cover_letter import CoverLetter

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "024_refine_loop.py"
)
EXPECTED = ["refine_messages", "final_text", "final_answers", "edit_distance_pct"]


def _load():
    spec = importlib.util.spec_from_file_location("mig_024_refine_loop", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_chain():
    mod = _load()
    assert mod.revision == "024_refine_loop"
    assert mod.down_revision == "023_generation_v2"


def test_upgrade_adds_columns(monkeypatch):
    mod = _load()
    fake_op = MagicMock()
    monkeypatch.setattr(mod, "op", fake_op)
    mod.upgrade()
    added = [(c.args[0], c.args[1].name) for c in fake_op.add_column.call_args_list]
    assert added == [("cover_letters", name) for name in EXPECTED]
    assert all(c.args[1].nullable for c in fake_op.add_column.call_args_list)


def test_downgrade_drops_columns_in_reverse(monkeypatch):
    mod = _load()
    fake_op = MagicMock()
    monkeypatch.setattr(mod, "op", fake_op)
    mod.downgrade()
    dropped = [c.args for c in fake_op.drop_column.call_args_list]
    assert dropped == [("cover_letters", name) for name in reversed(EXPECTED)]


def test_cover_letter_model_has_columns():
    cols = CoverLetter.__table__.c
    for name in EXPECTED:
        assert name in cols
        assert cols[name].nullable
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_migration_024.py
```
Expected: FAIL (`FileNotFoundError` for `024_refine_loop.py`, and `AssertionError` on `refine_messages`).

- [ ] **Step 3: Create the migration** `/Users/admin/dev2/UpApply/api/alembic/versions/024_refine_loop.py`

```python
"""Add refine-thread and submitted-final columns to cover_letters.

Revision ID: 024_refine_loop
Revises: 023_generation_v2
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '024_refine_loop'
down_revision = '023_generation_v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Refine thread: [{role, content, screening_answers?, warnings?, at}]
    op.add_column('cover_letters', sa.Column('refine_messages', postgresql.JSONB(), nullable=True))
    # What Chris actually submitted on Upwork (captured on Submit click)
    op.add_column('cover_letters', sa.Column('final_text', sa.Text(), nullable=True))
    op.add_column('cover_letters', sa.Column('final_answers', postgresql.JSONB(), nullable=True))
    # Word-level edit distance draft → final (0.0 identical, 1.0 rewritten)
    op.add_column('cover_letters', sa.Column('edit_distance_pct', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('cover_letters', 'edit_distance_pct')
    op.drop_column('cover_letters', 'final_answers')
    op.drop_column('cover_letters', 'final_text')
    op.drop_column('cover_letters', 'refine_messages')
```

- [ ] **Step 4: Add the ORM columns** in `/Users/admin/dev2/UpApply/api/app/models/cover_letter.py`

Change the import on line 6 from
```python
from sqlalchemy import DateTime, String, Text, Integer, Boolean, Numeric, func, ForeignKey
```
to
```python
from sqlalchemy import DateTime, String, Text, Integer, Boolean, Numeric, Float, func, ForeignKey
```
Insert this block directly above `    created_at: Mapped[datetime] = mapped_column(`:
```python
    # Refine + learn loop (migration 024)
    refine_messages: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    final_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_answers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    edit_distance_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

```

- [ ] **Step 5: Run the tests and the head check, and confirm they pass**

```bash
cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_migration_024.py && ./venv/bin/alembic heads
```
Expected: `4 passed`; `alembic heads` prints exactly one line, `024_refine_loop (head)`.

- [ ] **Step 6: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/alembic/versions/024_refine_loop.py api/app/models/cover_letter.py api/tests/test_migration_024.py
git commit -m "feat(db): migration 024 — cover_letters refine_messages, final_text, final_answers, edit_distance_pct

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.2: Refine service with the `search_facts` tool loop

**Files:**
- Create: `/Users/admin/dev2/UpApply/api/app/services/generation/refine.py`
- Create: `/Users/admin/dev2/UpApply/api/tests/test_refine_service.py`

**Interfaces:**
- Consumes: `get_anthropic_client() -> AsyncAnthropic`; `generate_embedding(text) -> list[float]`; `search_facts(db, user_id, query_embedding, limit=8, status='approved') -> list[tuple[Fact, float]]`; `check_rules(text, brief, preferred_closing) -> list[str]`; `async check_claims(draft, evidence) -> list[str]`; `JobBrief`, `Evidence(facts=..., voice_samples=...)`, `Draft(cover_letter, screening_answers, fact_ids_used)`, `finalize_letter(raw, preferred_closing)` (Phase 2 Task 2.6); `settings.cover_letter_model`, `settings.writer_effort`.
- Produces:
  - `MAX_TOOL_ROUNDS = 4`
  - `class RefineError(RuntimeError)`
  - `@dataclass class RefineResult: draft: Draft; warnings: list[str]; found_facts: list[Fact]`
  - `async refine_application(db, user_id: str, profile, brief: JobBrief, evidence: Evidence, current: Draft, history: list[dict], message: str) -> RefineResult`

Design notes:
- Opus 5.5 constraints: no `temperature`, no `thinking`, `output_config={"effort": ..., "format": json_schema}`, `tool_choice={"type": "auto"}`, no prefill.
- Each turn is sent as one fresh user message, with the earlier thread written into it as a transcript. Earlier assistant turns are not replayed, so preserved-thinking history checks never come into play.
- Inside a single turn the tool loop appends `resp.content` back unchanged. The system prompt and the context block (brief, evidence, voice samples) carry `cache_control`.

- [ ] **Step 1: Write the failing test** `/Users/admin/dev2/UpApply/api/tests/test_refine_service.py`

```python
"""Unit tests for the refine thread service (LLM, embeddings and fact search mocked)."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.models.fact import Fact
from app.models.proposal import Proposal
from app.services.generation.brief import JobBrief
from app.services.generation.evidence import Evidence
from app.services.generation.writer import Draft
from app.services.generation import refine as refine_mod
from app.services.generation.refine import (
    MAX_TOOL_ROUNDS,
    RefineError,
    refine_application,
)

MOD = "app.services.generation.refine"

EVIDENCE_FACT_ID = "11111111-1111-1111-1111-111111111111"
FOUND_FACT_ID = "22222222-2222-2222-2222-222222222222"


def _fact(fid: str, statement: str) -> Fact:
    return Fact(
        id=fid, user_id="u1", kind="project", statement=statement, detail=None,
        skills=[], industries=[], job_types=["cloud"], strength=0.9,
        status="approved", source_type="bio_memory", sources=[],
        times_used=0, times_in_won=0,
    )


def _brief() -> JobBrief:
    return JobBrief(
        needs=["has migrated prod SQL Server to Azure without downtime"],
        job_types=["cloud", "sql"],
        client_signals={"tone": "technical"},
        mirror_phrases=["zero downtime"],
        explicit_asks=[],
        questions=["What is your migration approach?"],
    )


def _evidence() -> Evidence:
    voice = Proposal(id="p1", user_id="u1", cover_letter_text="VOICE SAMPLE TEXT about a past job.")
    return Evidence(facts=[_fact(EVIDENCE_FACT_ID, "Led a 160-server on-prem to Azure migration.")],
                    voice_samples=[voice])


def _current() -> Draft:
    return Draft(
        cover_letter="Zero downtime is the whole job here.\n\nWarm regards,\nChris",
        screening_answers=[{"question": "What is your migration approach?", "answer": "Phased cutover."}],
        fact_ids_used=[EVIDENCE_FACT_ID],
    )


def _profile():
    return SimpleNamespace(full_name="Chris Therriault", preferred_closing="Chris")


def _tool_use(query: str, tool_id: str = "tu_1"):
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", id=tool_id, name="search_facts", input={"query": query})],
    )


def _final(payload: dict):
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=json.dumps(payload))],
    )


def _client(responses):
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=responses)
    return client


REVISED = {
    "cover_letter": "Zero downtime, proven on Azure.\n\nWarm regards,\nChris",
    "screening_answers": [{"question": "What is your migration approach?", "answer": "Phased cutover with rollback."}],
    "fact_ids_used": [EVIDENCE_FACT_ID, FOUND_FACT_ID],
}


@pytest.mark.asyncio
async def test_tool_loop_returns_revised_draft_and_found_facts():
    found = _fact(FOUND_FACT_ID, "Built AnalyzeMyCloud.com for Azure cost analysis.")
    client = _client([_tool_use("azure cost work"), _final(REVISED)])
    with patch(f"{MOD}.get_anthropic_client", return_value=client), \
         patch(f"{MOD}.generate_embedding", AsyncMock(return_value=[0.1] * 1536)), \
         patch(f"{MOD}.search_facts", AsyncMock(return_value=[(found, 0.81)])) as search, \
         patch(f"{MOD}.check_rules", return_value=["rule warning"]) as rules, \
         patch(f"{MOD}.check_claims", AsyncMock(return_value=["claim warning"])) as claims:
        result = await refine_application(
            None, "u1", _profile(), _brief(), _evidence(), _current(), [], "Mention the Azure cost work",
        )

    assert result.draft.cover_letter == REVISED["cover_letter"]
    assert result.draft.fact_ids_used == [EVIDENCE_FACT_ID, FOUND_FACT_ID]
    assert result.warnings == ["rule warning", "claim warning"]
    assert [str(f.id) for f in result.found_facts] == [FOUND_FACT_ID]
    search.assert_awaited_once()
    assert search.await_args.kwargs["limit"] == 5
    rules.assert_called_once_with(REVISED["cover_letter"], rules.call_args.args[1], "Chris")
    claim_evidence = claims.await_args.args[1]
    assert {str(f.id) for f in claim_evidence.facts} == {EVIDENCE_FACT_ID, FOUND_FACT_ID}

    # Second request carries the tool result back, after the unchanged assistant content
    second = client.messages.create.await_args_list[1].kwargs
    assert second["messages"][1]["role"] == "assistant"
    tool_result = second["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "tu_1"
    assert FOUND_FACT_ID in tool_result["content"]


@pytest.mark.asyncio
async def test_request_shape_obeys_opus_5_5_constraints():
    client = _client([_final(REVISED)])
    with patch(f"{MOD}.get_anthropic_client", return_value=client), \
         patch(f"{MOD}.check_rules", return_value=[]), \
         patch(f"{MOD}.check_claims", AsyncMock(return_value=[])):
        await refine_application(None, "u1", _profile(), _brief(), _evidence(), _current(),
                                 [{"role": "user", "content": "shorter please"},
                                  {"role": "assistant", "content": "older draft"}],
                                 "Now mention zero downtime twice")

    kwargs = client.messages.create.await_args.kwargs
    assert kwargs["model"] == settings.cover_letter_model
    assert "temperature" not in kwargs
    assert "thinking" not in kwargs
    assert kwargs["tool_choice"] == {"type": "auto"}
    assert kwargs["tools"][0]["name"] == "search_facts"
    assert kwargs["output_config"]["effort"] == settings.writer_effort
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}

    user_blocks = kwargs["messages"][0]["content"]
    context, turn = user_blocks[0]["text"], user_blocks[1]["text"]
    assert user_blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "has migrated prod SQL Server to Azure" in context
    assert "160-server" in context and EVIDENCE_FACT_ID in context
    assert "VOICE SAMPLE TEXT" in context
    assert "Zero downtime is the whole job here." in turn
    assert "Phased cutover." in turn
    assert "Chris: shorter please" in turn
    assert "Now mention zero downtime twice" in turn
    assert len(kwargs["messages"]) == 1  # prior turns are a transcript, never replayed assistant turns


@pytest.mark.asyncio
async def test_tool_loop_is_capped():
    client = _client([_tool_use("x", f"tu_{i}") for i in range(MAX_TOOL_ROUNDS + 1)])
    with patch(f"{MOD}.get_anthropic_client", return_value=client), \
         patch(f"{MOD}.generate_embedding", AsyncMock(return_value=[0.1] * 1536)), \
         patch(f"{MOD}.search_facts", AsyncMock(return_value=[])):
        with pytest.raises(RefineError):
            await refine_application(None, "u1", _profile(), _brief(), _evidence(), _current(), [], "go")
    assert client.messages.create.await_count == MAX_TOOL_ROUNDS + 1


@pytest.mark.asyncio
async def test_refusal_raises():
    client = _client([SimpleNamespace(stop_reason="refusal", content=[])])
    with patch(f"{MOD}.get_anthropic_client", return_value=client):
        with pytest.raises(RefineError):
            await refine_application(None, "u1", _profile(), _brief(), _evidence(), _current(), [], "go")


@pytest.mark.asyncio
async def test_proxy_rejecting_request_raises_refine_error():
    """Review focus: a proxy that rejects output_config/tools must surface as a 502, not a 500."""
    import httpx
    from anthropic import BadRequestError

    request = httpx.Request("POST", "https://proxy.example.com/v1/messages")
    error = BadRequestError(
        "output_config: Extra inputs are not permitted",
        response=httpx.Response(400, request=request),
        body=None,
    )
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=error)
    with patch(f"{MOD}.get_anthropic_client", return_value=client):
        with pytest.raises(RefineError, match="output_config"):
            await refine_application(None, "u1", _profile(), _brief(), _evidence(), _current(), [], "go")


@pytest.mark.asyncio
async def test_search_failure_is_reported_to_model_not_raised():
    client = _client([_tool_use("azure"), _final(REVISED)])
    with patch(f"{MOD}.get_anthropic_client", return_value=client), \
         patch(f"{MOD}.generate_embedding", AsyncMock(side_effect=RuntimeError("quota"))), \
         patch(f"{MOD}.check_rules", return_value=[]), \
         patch(f"{MOD}.check_claims", AsyncMock(return_value=[])):
        result = await refine_application(None, "u1", _profile(), _brief(), _evidence(), _current(), [], "go")
    tool_result = client.messages.create.await_args_list[1].kwargs["messages"][2]["content"][0]
    assert tool_result["is_error"] is True
    assert result.found_facts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["not json", '{"cover_letter": "x"}', '{"cover_letter": "x", "screening_answers": []'])
async def test_invalid_or_partial_json_raises_refine_error(text):
    bad = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])
    with patch(f"{MOD}.get_anthropic_client", return_value=_client([bad])):
        with pytest.raises(RefineError):
            await refine_application(None, "u1", _profile(), _brief(), _evidence(), _current(), [], "go")


@pytest.mark.asyncio
async def test_closing_is_normalised_in_code():
    no_closing = {**REVISED, "cover_letter": "Zero downtime, proven on Azure.\n\nBest,\nC."}
    with patch(f"{MOD}.get_anthropic_client", return_value=_client([_final(no_closing)])), \
         patch(f"{MOD}.check_rules", return_value=[]), \
         patch(f"{MOD}.check_claims", AsyncMock(return_value=[])):
        result = await refine_application(None, "u1", _profile(), _brief(), _evidence(), _current(), [], "go")
    assert result.draft.cover_letter == "Zero downtime, proven on Azure.\n\nWarm regards,\nChris"


def test_draft_schema_is_strict():
    schema = refine_mod.DRAFT_SCHEMA
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"cover_letter", "screening_answers", "fact_ids_used"}
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_refine_service.py
```
Expected: FAIL (`ModuleNotFoundError: No module named 'app.services.generation.refine'`).

- [ ] **Step 3: Implement** `/Users/admin/dev2/UpApply/api/app/services/generation/refine.py`

```python
"""Refine thread (spec §3.1): revise a v2 draft from one message of Chris's feedback.

Every turn re-sends the same brief, evidence, voice samples and current draft
(cached prefix) plus the thread so far. The model has one tool, search_facts, over
Chris's approved facts so a request like "mention the Azure work" cites a real fact.
Verify (rules + claim check) runs on every revised draft.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from anthropic import APIError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.embeddings import generate_embedding
from app.models.fact import Fact
from app.services.facts import search_facts
from app.services.generation.brief import JobBrief
from app.services.generation.evidence import Evidence
from app.services.generation.verify import check_claims, check_rules
from app.services.generation.writer import Draft, finalize_letter
from app.services.llm import PROXY_HINT, get_anthropic_client

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4

SEARCH_FACTS_TOOL = {
    "name": "search_facts",
    "description": (
        "Search Chris's approved fact library (projects, metrics, credentials, client quotes, "
        "roles, tech, outcomes). Use it whenever the requested change needs a specific claim "
        "that is not already in EVIDENCE, for example 'mention the Azure work'. Returns up to "
        "5 facts with ids. Only cite facts this tool or EVIDENCE returned."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The kind of experience to look for, in plain words.",
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "cover_letter": {"type": "string"},
        "screening_answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "required": ["question", "answer"],
                "additionalProperties": False,
            },
        },
        "fact_ids_used": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["cover_letter", "screening_answers", "fact_ids_used"],
    "additionalProperties": False,
}


class RefineError(RuntimeError):
    """The model could not produce a revised draft (refusal, truncation, tool-loop cap)."""


@dataclass
class RefineResult:
    draft: Draft
    warnings: list[str]
    found_facts: list[Fact] = field(default_factory=list)


def _system_prompt(profile) -> str:
    name = profile.full_name or "the freelancer"
    return (
        f"You revise Upwork job applications written in {name}'s own voice, one round of "
        "feedback at a time.\n\n"
        "Rules that always hold:\n"
        '- No sentence may begin with the word "I".\n'
        "- No salutation (Hello, Hi, Dear) at the start of the letter.\n"
        "- Do not write a sign-off or closing; the closing line is appended automatically.\n"
        "- Specific claims (numbers, client names, named projects, outcomes) may only come from "
        "EVIDENCE, from search_facts results, or from facts Chris states in his feedback. If a "
        "requested claim cannot be found, leave it out rather than inventing it.\n"
        "- Change what the feedback asks for and keep everything else as close to the current "
        "draft as possible. Match the voice samples.\n\n"
        "Return the full revised cover letter, an answer for every screening question in the "
        "brief, and the ids of every fact the revised letter or answers rely on."
    )


def _context_block(brief: JobBrief, evidence: Evidence) -> str:
    facts = "\n".join(
        f"[{f.id}] ({f.kind}) {f.statement}" + (f" | {f.detail}" if f.detail else "")
        for f in evidence.facts
    )
    voice = "\n\n---\n\n".join(p.cover_letter_text for p in evidence.voice_samples)
    return (
        f"JOB BRIEF:\n{brief.model_dump_json(indent=2)}\n\n"
        f"EVIDENCE (approved facts, cite by id):\n{facts or '(none)'}\n\n"
        f"VOICE SAMPLES (write the way these read):\n{voice or '(none)'}"
    )


def _turn_block(current: Draft, history: list[dict], message: str) -> str:
    transcript = "\n".join(
        f"Chris: {h['content']}" if h["role"] == "user" else "(draft revised)"
        for h in history
    )
    answers = "\n".join(
        f"Q: {a['question']}\nA: {a['answer']}" for a in current.screening_answers
    )
    prefix = f"REFINE THREAD SO FAR:\n{transcript}\n\n" if transcript else ""
    return (
        f"{prefix}CURRENT DRAFT:\n{current.cover_letter}\n\n"
        f"CURRENT SCREENING ANSWERS:\n{answers or '(none)'}\n\n"
        f"CHRIS'S NEW FEEDBACK:\n{message}"
    )


async def _run_search(
    db: AsyncSession, user_id: str, block: Any, found: dict[str, Fact]
) -> dict:
    query = str((block.input or {}).get("query", "")).strip()
    if not query:
        return {"type": "tool_result", "tool_use_id": block.id,
                "content": "Empty query.", "is_error": True}
    try:
        embedding = await generate_embedding(query)
        hits = await search_facts(db, user_id, embedding, limit=5)
    except Exception as exc:
        logger.warning("search_facts tool failed for user %s: %s", user_id, exc)
        return {"type": "tool_result", "tool_use_id": block.id,
                "content": "Fact search is unavailable right now.", "is_error": True}
    for fact, _similarity in hits:
        found[str(fact.id)] = fact
    payload = [
        {"id": str(f.id), "kind": f.kind, "statement": f.statement, "detail": f.detail}
        for f, _similarity in hits
    ]
    return {
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": json.dumps(payload) if payload else "No approved facts match that query.",
    }


async def refine_application(
    db: AsyncSession,
    user_id: str,
    profile,
    brief: JobBrief,
    evidence: Evidence,
    current: Draft,
    history: list[dict],
    message: str,
) -> RefineResult:
    """Run one refine turn: tool loop over search_facts, then verify the revised draft."""
    client = get_anthropic_client()
    system = [{"type": "text", "text": _system_prompt(profile),
               "cache_control": {"type": "ephemeral"}}]
    messages: list[dict] = [{
        "role": "user",
        "content": [
            {"type": "text", "text": _context_block(brief, evidence),
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": _turn_block(current, history, message)},
        ],
    }]
    found: dict[str, Fact] = {}

    for _ in range(MAX_TOOL_ROUNDS + 1):
        try:
            resp = await client.messages.create(
                model=settings.cover_letter_model,
                max_tokens=16000,
                system=system,
                messages=messages,
                tools=[SEARCH_FACTS_TOOL],
                tool_choice={"type": "auto"},
                output_config={
                    "effort": settings.writer_effort,
                    "format": {"type": "json_schema", "schema": DRAFT_SCHEMA},
                },
            )
        except APIError as exc:
            # e.g. a proxy (ANTHROPIC_BASE_URL) that rejects output_config or tools → 502, not 500
            raise RefineError(f"Refine API error: {exc} ({PROXY_HINT})") from exc
        if resp.stop_reason == "refusal":
            raise RefineError("The model declined this refine request.")
        if resp.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": resp.content})
        results = [
            await _run_search(db, user_id, block, found)
            for block in resp.content
            if block.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})
    else:
        raise RefineError("Refine exceeded the fact-search limit; try a narrower request.")

    if resp.stop_reason == "max_tokens":
        raise RefineError("Refine response was truncated.")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if text is None:
        raise RefineError("Refine returned no draft.")
    try:
        parsed = Draft(**json.loads(text))
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        logger.warning("Refine returned unusable JSON: %.200s", text)
        raise RefineError("Refine returned an unreadable draft; try again.") from exc
    # Same post-processing as the first draft (Task 2.6): the closing is always set in code.
    draft = Draft(
        cover_letter=finalize_letter(parsed.cover_letter, profile.preferred_closing),
        screening_answers=parsed.screening_answers,
        fact_ids_used=parsed.fact_ids_used,
    )

    merged = {str(f.id): f for f in evidence.facts}
    merged.update(found)
    all_evidence = Evidence(facts=list(merged.values()), voice_samples=evidence.voice_samples)
    warnings = check_rules(draft.cover_letter, brief, profile.preferred_closing)
    warnings += await check_claims(draft, all_evidence)
    return RefineResult(draft=draft, warnings=warnings, found_facts=list(found.values()))
```

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_refine_service.py
```
Expected: `11 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/services/generation/refine.py api/tests/test_refine_service.py
git commit -m "feat(generation): refine thread service with search_facts tool loop and per-turn verify

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.3: `POST /jobs/cover-letters/{id}/refine` (30/hr)

**Files:**
- Modify: `/Users/admin/dev2/UpApply/api/app/schemas/job.py` (append after `class CoverLetterImproveResponse`, currently lines 175–181)
- Modify: `/Users/admin/dev2/UpApply/api/app/api/v1/jobs.py` (imports lines 1–50; new helper and endpoint inserted directly above the `# Attachment extraction endpoints` comment, currently line 1170)
- Create: `/Users/admin/dev2/UpApply/api/tests/test_refine_loop_api.py`

**Interfaces:**
- Consumes: `refine_application`, `RefineError`, `RefineResult` (Task 3.2); `extract_facts(text, source_type, source_ref=None, context=None)`; `upsert_candidate(db, user_id, cand, auto_approve=False)`; `JobBrief.model_validate`; `Evidence`; `Draft`.
- Produces:
  - Schemas `QAPair(question, answer)`; `CoverLetterRefineRequest(message: str, screening_answers: Optional[List[QAPair]] = None)`; `CoverLetterRefineResponse(cover_letter, screening_answers: List[QAPair], warnings: List[str], refine_messages: List[dict])`; `CoverLetterFinalRequest(final_text, final_answers: Optional[List[QAPair]] = None)`; `CoverLetterFinalResponse(id, edit_distance_pct, author, proposal_id, fact_candidates)` (the final schemas are used by Task 3.4).
  - `POST /api/v1/jobs/cover-letters/{letter_id}/refine` → `CoverLetterRefineResponse`. Returns 404 for an unknown or foreign letter, 409 when the letter has no `brief` (it was not generated by v2), 422 for a blank message, 502 on `RefineError`.
  - The private helper `_capture_fact_candidates(db, user_id, text, source_type, source_ref, context=None) -> int` in `jobs.py`, reused by Task 3.4.

Behaviour: the current draft is `letter.content`. Its answers come from the last assistant entry in `refine_messages`; on the first turn they come from the request's `screening_answers`. The letter is updated in place, so the id stays stable for `PUT /final`. `fact_ids_used` gains only ids from evidence or `found_facts`, and each newly used fact gets `times_used += 1`. Two entries are appended to `refine_messages`. Chris's message goes to fact extraction (`source_type="refine_thread"`) inside a savepoint, so a failure there never breaks the refine.

- [ ] **Step 1: Write the failing test** `/Users/admin/dev2/UpApply/api/tests/test_refine_loop_api.py`

```python
"""API tests for the refine + final endpoints (LLM, embeddings and extraction mocked)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.cover_letter import CoverLetter
from app.models.fact import Fact
from app.models.job import Job
from app.models.proposal import Proposal
from app.schemas.fact import FactCandidate
from app.services.generation.refine import RefineError, RefineResult
from app.services.generation.writer import Draft
from tests.conftest import TestSessionLocal

JOBS = "app.api.v1.jobs"
BRIEF = {
    "needs": ["has migrated prod SQL Server to Azure without downtime"],
    "job_types": ["cloud", "sql"],
    "client_signals": {},
    "mirror_phrases": [],
    "explicit_asks": [],
    "questions": ["What is your migration approach?"],
}
ORIGINAL = (
    "Zero downtime is the whole job here. The 160-server Azure move ran with no outage "
    "because every cutover had a rehearsed rollback.\n\nWarm regards,\nChris"
)


async def _user_id(client: AsyncClient, headers: dict) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


async def _seed_fact(user_id: str, statement: str) -> str:
    async with TestSessionLocal() as s:
        fact = Fact(
            user_id=user_id, kind="project", statement=statement, detail=None,
            skills=["Azure"], industries=[], job_types=["cloud"], strength=0.9,
            status="approved", source_type="bio_memory", source_ref=None, sources=[],
            times_used=0, times_in_won=0, embedding=[0.1] * 1536,
        )
        s.add(fact)
        await s.commit()
        return str(fact.id)


async def _seed_letter(user_id: str, *, brief: dict | None = BRIEF, fact_ids=None) -> tuple[str, str]:
    async with TestSessionLocal() as s:
        job = Job(
            user_id=user_id, upwork_url="https://www.upwork.com/jobs/~01abc",
            title="Azure SQL migration lead",
            description="Move our SQL Server estate to Azure without downtime.",
            skills_required=["Azure", "SQL Server"],
        )
        s.add(job)
        await s.flush()
        letter = CoverLetter(
            user_id=user_id, job_id=job.id, content=ORIGINAL, model_used="claude-opus-5-5",
            brief=brief, fact_ids_used=fact_ids or [], voice_sample_ids=[], version=1,
        )
        s.add(letter)
        await s.commit()
        return job.id, letter.id


async def _letter(letter_id: str) -> CoverLetter:
    async with TestSessionLocal() as s:
        return (await s.execute(select(CoverLetter).where(CoverLetter.id == letter_id))).scalar_one()


@pytest.mark.asyncio
async def test_refine_updates_letter_thread_and_facts(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    used_id = await _seed_fact(uid, "Led a 160-server on-prem to Azure migration.")
    found_id = await _seed_fact(uid, "Built AnalyzeMyCloud.com for Azure cost analysis.")
    _, letter_id = await _seed_letter(uid, fact_ids=[used_id])

    async with TestSessionLocal() as s:
        found_fact = (await s.execute(select(Fact).where(Fact.id == found_id))).scalar_one()
    revised = "Zero downtime, proven on Azure, with cost analysis built in.\n\nWarm regards,\nChris"
    result = RefineResult(
        draft=Draft(
            cover_letter=revised,
            screening_answers=[{"question": "What is your migration approach?", "answer": "Phased cutover."}],
            fact_ids_used=[used_id, found_id, "not-a-real-fact"],
        ),
        warnings=["Sentence starts with 'I'"],
        found_facts=[found_fact],
    )
    cand = FactCandidate(kind="metric", statement="The Azure migration covered 160 servers.",
                         source_type="refine_thread")
    with patch(f"{JOBS}.refine_application", AsyncMock(return_value=result)) as refine, \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[cand])) as extract, \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()) as upsert:
        r = await client.post(
            f"/api/v1/jobs/cover-letters/{letter_id}/refine",
            headers=auth_headers_with_profile,
            json={"message": "It was 160 servers, and mention the cost work",
                  "screening_answers": [{"question": "What is your migration approach?", "answer": "Big bang."}]},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cover_letter"] == revised
    assert body["warnings"] == ["Sentence starts with 'I'"]
    assert body["screening_answers"][0]["answer"] == "Phased cutover."
    assert [m["role"] for m in body["refine_messages"]] == ["user", "assistant"]

    current = refine.await_args.args[5]
    assert current.cover_letter == ORIGINAL
    assert current.screening_answers == [{"question": "What is your migration approach?", "answer": "Big bang."}]
    assert refine.await_args.args[7] == "It was 160 servers, and mention the cost work"
    extract.assert_awaited_once()
    assert extract.await_args.args[1] == "refine_thread"
    upsert.assert_awaited_once()

    letter = await _letter(letter_id)
    assert letter.content == revised
    assert {str(x) for x in letter.fact_ids_used} == {used_id, found_id}
    assert len(letter.refine_messages) == 2
    async with TestSessionLocal() as s:
        times = dict((await s.execute(select(Fact.id, Fact.times_used))).all())
    assert times[found_fact.id] == 1          # newly used via search_facts
    assert sum(times.values()) == 1           # the already-used fact is not double counted


@pytest.mark.asyncio
async def test_second_turn_uses_answers_from_thread(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    async with TestSessionLocal() as s:
        letter = (await s.execute(select(CoverLetter).where(CoverLetter.id == letter_id))).scalar_one()
        letter.refine_messages = [
            {"role": "user", "content": "shorter", "at": "2026-10-12T00:00:00+00:00"},
            {"role": "assistant", "content": ORIGINAL, "warnings": [], "at": "2026-10-12T00:00:00+00:00",
             "screening_answers": [{"question": "What is your migration approach?", "answer": "From thread."}]},
        ]
        await s.commit()

    result = RefineResult(draft=Draft(cover_letter=ORIGINAL, screening_answers=[], fact_ids_used=[]),
                          warnings=[], found_facts=[])
    with patch(f"{JOBS}.refine_application", AsyncMock(return_value=result)) as refine, \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])), \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()):
        r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                              headers=auth_headers_with_profile,
                              json={"message": "warmer", "screening_answers": [
                                  {"question": "What is your migration approach?", "answer": "Ignored."}]})
    assert r.status_code == 200, r.text
    assert refine.await_args.args[5].screening_answers[0]["answer"] == "From thread."
    assert len(refine.await_args.args[6]) == 2
    assert len(r.json()["refine_messages"]) == 4


@pytest.mark.asyncio
async def test_refine_rejects_non_v2_letter(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid, brief=None)
    r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                          headers=auth_headers_with_profile, json={"message": "shorter"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_refine_blank_message_and_unknown_letter(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                          headers=auth_headers_with_profile, json={"message": "   "})
    assert r.status_code == 422
    r = await client.post("/api/v1/jobs/cover-letters/00000000-0000-0000-0000-000000000000/refine",
                          headers=auth_headers_with_profile, json={"message": "shorter"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_refine_model_failure_is_502(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    with patch(f"{JOBS}.refine_application", AsyncMock(side_effect=RefineError("declined"))):
        r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                              headers=auth_headers_with_profile, json={"message": "shorter"})
    assert r.status_code == 502
    assert (await _letter(letter_id)).refine_messages is None


@pytest.mark.asyncio
async def test_fact_capture_failure_does_not_break_refine(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    _, letter_id = await _seed_letter(uid)
    result = RefineResult(draft=Draft(cover_letter="New text.\n\nWarm regards,\nChris",
                                      screening_answers=[], fact_ids_used=[]),
                          warnings=[], found_facts=[])
    with patch(f"{JOBS}.refine_application", AsyncMock(return_value=result)), \
         patch(f"{JOBS}.extract_facts", AsyncMock(side_effect=RuntimeError("haiku down"))):
        r = await client.post(f"/api/v1/jobs/cover-letters/{letter_id}/refine",
                              headers=auth_headers_with_profile, json={"message": "shorter"})
    assert r.status_code == 200, r.text
    assert (await _letter(letter_id)).content.startswith("New text.")
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_refine_loop_api.py
```
Expected: FAIL (`AttributeError: <module 'app.api.v1.jobs'> does not have the attribute 'refine_application'`, plus 404/405 on the route).

- [ ] **Step 3: Add the schemas** by appending to `/Users/admin/dev2/UpApply/api/app/schemas/job.py`, directly after the `CoverLetterImproveResponse` class:

```python
class QAPair(BaseModel):
    """One screening question and its answer."""

    question: str
    answer: str


class CoverLetterRefineRequest(BaseModel):
    """One refine-thread message from the user."""

    message: str
    # Sidebar's current answers; only read on the first turn (later turns use the thread)
    screening_answers: Optional[List[QAPair]] = None


class CoverLetterRefineResponse(BaseModel):
    """Revised draft after one refine turn."""

    cover_letter: str
    screening_answers: List[QAPair]
    warnings: List[str]
    refine_messages: List[dict]


class CoverLetterFinalRequest(BaseModel):
    """What was actually submitted on Upwork (captured on Submit click)."""

    final_text: str
    final_answers: Optional[List[QAPair]] = None


class CoverLetterFinalResponse(BaseModel):
    """Result of recording the submitted text."""

    id: str
    edit_distance_pct: float
    author: str  # chris | chris_edited_ai
    proposal_id: Optional[str] = None
    fact_candidates: int
```

- [ ] **Step 4: Wire the imports** in `/Users/admin/dev2/UpApply/api/app/api/v1/jobs.py`

Change line 2 `from datetime import datetime, timezone` to:
```python
import logging
from datetime import datetime, timezone
```
Inside the `from app.schemas.job import (` list, add these names after `CoverLetterImproveResponse,`:
```python
    CoverLetterRefineRequest,
    CoverLetterRefineResponse,
    CoverLetterFinalRequest,
    CoverLetterFinalResponse,
```
Replace the line `router = APIRouter()` with:
```python
from app.models.fact import Fact
from app.services.facts import credit_facts, upsert_candidate
from app.services.fact_extraction import extract_facts
from app.services.generation.brief import JobBrief
from app.services.generation.evidence import Evidence
from app.services.generation.writer import Draft
from app.services.generation.refine import RefineError, refine_application

logger = logging.getLogger(__name__)
router = APIRouter()
```
(Phase 2 Task 2.8 added only `from app.services.generation import generate_application` and `from app.services.llm import LLMError` to this module, so none of these names is imported yet.)

- [ ] **Step 5: Add the helper and endpoint** to `/Users/admin/dev2/UpApply/api/app/api/v1/jobs.py`, directly above the line `# Attachment extraction endpoints`:

```python
# ---------------------------------------------------------------------------
# Refine + learn loop (spec §3)
# ---------------------------------------------------------------------------

async def _capture_fact_candidates(
    db: AsyncSession,
    user_id: str,
    text: str,
    source_type: str,
    source_ref: Optional[str],
    context: Optional[str] = None,
) -> int:
    """Turn the user's own words into fact candidates. Never fails the request."""
    try:
        candidates = await extract_facts(text, source_type, source_ref=source_ref, context=context)
        async with db.begin_nested():
            for cand in candidates:
                await upsert_candidate(db, user_id, cand)
        return len(candidates)
    except Exception as exc:
        logger.warning("Fact capture failed (%s %s): %s", source_type, source_ref, exc)
        return 0


@router.post("/cover-letters/{letter_id}/refine", response_model=CoverLetterRefineResponse)
@limiter.limit("30/hour")
async def refine_cover_letter_endpoint(
    request: Request,
    letter_id: str,
    body: CoverLetterRefineRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revise a v2 draft from one refine-thread message (search_facts tool, verify every turn)."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message is empty")

    result = await db.execute(
        select(CoverLetter).where(
            CoverLetter.id == letter_id,
            CoverLetter.user_id == current_user.id,
        )
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found")
    if not letter.brief:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Refine needs a letter generated by the v2 engine. Generate a new draft first.",
        )
    profile = await get_user_profile(current_user, db)

    brief = JobBrief.model_validate(letter.brief)
    known_ids = [str(x) for x in (letter.fact_ids_used or [])]
    facts = []
    if known_ids:
        facts = list((await db.execute(
            select(Fact).where(Fact.id.in_(known_ids), Fact.user_id == current_user.id)
        )).scalars())
    voice = []
    if letter.voice_sample_ids:
        voice = list((await db.execute(
            select(Proposal).where(
                Proposal.id.in_([str(x) for x in letter.voice_sample_ids]),
                Proposal.user_id == current_user.id,
            )
        )).scalars())

    history = list(letter.refine_messages or [])
    last = next((m for m in reversed(history) if m["role"] == "assistant"), None)
    current = Draft(
        cover_letter=letter.content,
        screening_answers=(
            last.get("screening_answers", []) if last
            else [a.model_dump() for a in (body.screening_answers or [])]
        ),
        fact_ids_used=known_ids,
    )

    try:
        outcome = await refine_application(
            db, current_user.id, profile, brief,
            Evidence(facts=facts, voice_samples=voice), current, history, message,
        )
    except RefineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    draft = outcome.draft
    allowed = set(known_ids) | {str(f.id) for f in outcome.found_facts}
    new_ids = [fid for fid in dict.fromkeys(draft.fact_ids_used) if fid in allowed and fid not in known_ids]
    if new_ids:
        letter.fact_ids_used = [*(letter.fact_ids_used or []), *new_ids]
        await credit_facts(db, new_ids, won=False)  # times_used += 1 (Phase 1 Task 1.4)

    now = datetime.now(timezone.utc).isoformat()
    letter.content = draft.cover_letter
    letter.word_count = len(draft.cover_letter.split())
    letter.model_used = settings.cover_letter_model
    letter.refine_messages = [
        *history,
        {"role": "user", "content": message, "at": now},
        {
            "role": "assistant",
            "content": draft.cover_letter,
            "screening_answers": draft.screening_answers,
            "warnings": outcome.warnings,
            "at": now,
        },
    ]
    await _capture_fact_candidates(
        db, current_user.id, message, "refine_thread", letter.id,
        context="; ".join(brief.needs) or None,
    )
    await db.commit()

    return CoverLetterRefineResponse(
        cover_letter=draft.cover_letter,
        screening_answers=draft.screening_answers,
        warnings=outcome.warnings,
        refine_messages=letter.refine_messages,
    )
```

- [ ] **Step 6: Run the tests and confirm they pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_refine_loop_api.py
```
Expected: `6 passed`.

- [ ] **Step 7: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/schemas/job.py api/app/api/v1/jobs.py api/tests/test_refine_loop_api.py
git commit -m "feat(api): POST /jobs/cover-letters/{id}/refine — threaded refine with fact search, verify, fact capture (30/hr)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.4: `PUT /jobs/cover-letters/{id}/final` — submitted text, voice sample, fact candidates

**Files:**
- Modify: `/Users/admin/dev2/UpApply/api/app/api/v1/jobs.py` (one import; new endpoint directly below `refine_cover_letter_endpoint`)
- Modify: `/Users/admin/dev2/UpApply/api/tests/test_refine_loop_api.py` (append tests)

**Interfaces:**
- Consumes: `word_edit_distance_pct(original, edited) -> float` (`app/services/edit_distance.py`); `generate_embedding`; `_capture_fact_candidates` (Task 3.3); `CoverLetterFinalRequest` and `CoverLetterFinalResponse` (Task 3.3); `Proposal.author`, `Proposal.job_text`, `Proposal.screening_answers`, `Proposal.job_needs_embedding`, `Proposal.facts_ingested_at` (Phase 1 Task 1.1).
- Produces: `PUT /api/v1/jobs/cover-letters/{letter_id}/final` → `CoverLetterFinalResponse`, plus the module constant `CHRIS_REWRITE_THRESHOLD = 0.9`.

Behaviour:
- Stores `final_text`, `final_answers` and `edit_distance_pct` (letter content vs final text). It also sets the legacy `submitted_text`, `was_submitted`, `submitted_at` and `is_final`.
- Upserts the `source="extension"` proposal for `(user, job)` as a voice sample. `author` is `chris` when `edit_distance_pct >= 0.9`, otherwise `chris_edited_ai`. `job_text` is the job description (the same meaning as Phase 1 Task 1.8; the title stays in `job_title`), and both embeddings are filled best-effort. `job_needs_embedding` embeds `"{title}\n\n{description}"`, the same text shape as Phase 1 Task 1.8 and Phase 2's voice-sample query.
- Extracts fact candidates from the final text plus the answers (`source_type="upwork_submission"`).
- A repeated capture with identical text (for example a double click) skips the embeddings and fact extraction.

- [ ] **Step 1: Write the failing tests** by appending to `/Users/admin/dev2/UpApply/api/tests/test_refine_loop_api.py`:

```python
async def _extension_proposal(user_id: str, job_id: str) -> Proposal | None:
    async with TestSessionLocal() as s:
        return (await s.execute(select(Proposal).where(
            Proposal.user_id == user_id, Proposal.job_id == job_id, Proposal.source == "extension",
        ))).scalars().first()


@pytest.mark.asyncio
async def test_final_light_edit_is_chris_edited_ai(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    job_id, letter_id = await _seed_letter(uid)
    edited = ORIGINAL.replace("rehearsed rollback", "rehearsed and timed rollback")
    with patch(f"{JOBS}.generate_embedding", AsyncMock(return_value=[0.2] * 1536)) as embed, \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[
             FactCandidate(kind="outcome", statement="No outage across 160 cutovers.",
                           source_type="upwork_submission")])) as extract, \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()) as upsert:
        r = await client.put(
            f"/api/v1/jobs/cover-letters/{letter_id}/final",
            headers=auth_headers_with_profile,
            json={"final_text": edited,
                  "final_answers": [{"question": "What is your migration approach?", "answer": "Phased."}]},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["author"] == "chris_edited_ai"
    assert 0 < body["edit_distance_pct"] < 0.9
    assert body["fact_candidates"] == 1
    assert embed.await_count == 2  # letter text + job text
    assert "Q: What is your migration approach?\nA: Phased." in extract.await_args.args[0]
    assert extract.await_args.args[1] == "upwork_submission"
    upsert.assert_awaited_once()

    letter = await _letter(letter_id)
    assert letter.final_text == edited
    assert letter.final_answers == [{"question": "What is your migration approach?", "answer": "Phased."}]
    assert letter.was_submitted is True and letter.is_final is True
    prop = await _extension_proposal(uid, job_id)
    assert prop.id == body["proposal_id"]
    assert prop.author == "chris_edited_ai"
    assert prop.screening_answers == [{"question": "What is your migration approach?", "answer": "Phased."}]
    assert prop.facts_ingested_at is not None
    assert prop.cover_letter_text == edited
    assert prop.job_text == "Move our SQL Server estate to Azure without downtime."
    assert prop.job_needs_embedding is not None


@pytest.mark.asyncio
async def test_final_rewrite_is_chris_and_repeat_is_idempotent(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    job_id, letter_id = await _seed_letter(uid)
    rewritten = ("Your estate sounds like the hospital network we moved last spring. "
                 "Happy to walk you through my plan on a call this week.\n\nThanks,\nC. Therriault")
    with patch(f"{JOBS}.generate_embedding", AsyncMock(return_value=[0.2] * 1536)), \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])) as extract, \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()):
        first = await client.put(f"/api/v1/jobs/cover-letters/{letter_id}/final",
                                 headers=auth_headers_with_profile, json={"final_text": rewritten})
        second = await client.put(f"/api/v1/jobs/cover-letters/{letter_id}/final",
                                  headers=auth_headers_with_profile, json={"final_text": rewritten})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["author"] == "chris"
    assert first.json()["edit_distance_pct"] >= 0.9
    assert extract.await_count == 1
    assert second.json()["proposal_id"] == first.json()["proposal_id"]
    async with TestSessionLocal() as s:
        count = len((await s.execute(select(Proposal).where(Proposal.job_id == job_id))).scalars().all())
    assert count == 1


@pytest.mark.asyncio
async def test_final_survives_embedding_outage(client, auth_headers_with_profile):
    uid = await _user_id(client, auth_headers_with_profile)
    job_id, letter_id = await _seed_letter(uid)
    with patch(f"{JOBS}.generate_embedding", AsyncMock(side_effect=RuntimeError("quota"))), \
         patch(f"{JOBS}.extract_facts", AsyncMock(return_value=[])), \
         patch(f"{JOBS}.upsert_candidate", AsyncMock()):
        r = await client.put(f"/api/v1/jobs/cover-letters/{letter_id}/final",
                             headers=auth_headers_with_profile, json={"final_text": ORIGINAL})
    assert r.status_code == 200, r.text
    assert r.json()["edit_distance_pct"] == 0.0
    prop = await _extension_proposal(uid, job_id)
    assert prop.embedding is None and prop.job_needs_embedding is None


@pytest.mark.asyncio
async def test_final_unknown_letter_404(client, auth_headers_with_profile):
    r = await client.put("/api/v1/jobs/cover-letters/00000000-0000-0000-0000-000000000000/final",
                         headers=auth_headers_with_profile, json={"final_text": "x"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_refine_loop_api.py -k final
```
Expected: FAIL (405 Method Not Allowed / 404 on `PUT .../final`).

- [ ] **Step 3: Implement.** In `/Users/admin/dev2/UpApply/api/app/api/v1/jobs.py`, add `from app.services.edit_distance import word_edit_distance_pct` to the import block added in Task 3.3 (above `logger = logging.getLogger(__name__)`). Then insert directly below `refine_cover_letter_endpoint`:

```python
CHRIS_REWRITE_THRESHOLD = 0.9  # ≥90% of words changed → treat the submission as Chris's own text


async def _embed_or_none(text: str) -> Optional[List[float]]:
    try:
        return await generate_embedding(text)
    except Exception as exc:
        logger.warning("Embedding failed (%d chars): %s", len(text), exc)
        return None


@router.put("/cover-letters/{letter_id}/final", response_model=CoverLetterFinalResponse)
async def submit_final_cover_letter(
    letter_id: str,
    body: CoverLetterFinalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record what was actually submitted on Upwork → voice sample + fact candidates."""
    result = await db.execute(
        select(CoverLetter).where(
            CoverLetter.id == letter_id,
            CoverLetter.user_id == current_user.id,
        )
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found")

    job = (await db.execute(select(Job).where(Job.id == letter.job_id))).scalar_one_or_none()
    answers = [a.model_dump() for a in (body.final_answers or [])]
    already_captured = letter.final_text == body.final_text
    edit_pct = word_edit_distance_pct(letter.content, body.final_text)
    author = "chris" if edit_pct >= CHRIS_REWRITE_THRESHOLD else "chris_edited_ai"
    now = datetime.now(timezone.utc)

    letter.final_text = body.final_text
    letter.final_answers = answers
    letter.edit_distance_pct = edit_pct
    letter.submitted_text = body.final_text
    letter.was_submitted = True
    letter.submitted_at = letter.submitted_at or now
    letter.is_final = True

    prop = (await db.execute(
        select(Proposal).where(
            Proposal.user_id == current_user.id,
            Proposal.job_id == letter.job_id,
            Proposal.source == "extension",
        )
    )).scalars().first()
    if prop is None:
        prop = Proposal(
            user_id=current_user.id,
            job_id=letter.job_id,
            cover_letter_text=body.final_text,
            job_title=job.title if job else None,
            job_skills=(job.skills_required or []) if job else [],
            source="extension",
            status="submitted",
            submitted_at=now,
        )
        db.add(prop)
    # Same meaning as Phase 1 Task 1.8: job_text is the job description only (title lives in job_title)
    job_text = (job.description or None) if job else None
    prop.cover_letter_text = body.final_text
    prop.author = author
    prop.job_text = job_text
    prop.screening_answers = answers or None  # voice-sample answers (Phase 1 column)
    if not already_captured:
        prop.embedding = await _embed_or_none(body.final_text)
        if job:
            # Same text shape as Phase 1 Task 1.8 and Phase 2 select_evidence's voice query
            prop.job_needs_embedding = await _embed_or_none(
                "\n\n".join(t for t in (job.title, job.description) if t)
            )
    await db.flush()

    fact_candidates = 0
    if not already_captured:
        qa = "\n\n".join(f"Q: {a['question']}\nA: {a['answer']}" for a in answers if a["answer"])
        fact_candidates = await _capture_fact_candidates(
            db, current_user.id,
            body.final_text + (f"\n\n{qa}" if qa else ""),
            "upwork_submission", letter.id,
            context=job.title if job else None,
        )
        # Already extracted here, so /facts/from-proposals (Phase 1 Task 1.6) skips this letter
        prop.facts_ingested_at = datetime.now(timezone.utc)
    await db.commit()

    return CoverLetterFinalResponse(
        id=letter.id,
        edit_distance_pct=edit_pct,
        author=author,
        proposal_id=prop.id,
        fact_candidates=fact_candidates,
    )
```

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_refine_loop_api.py
```
Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/api/v1/jobs.py api/tests/test_refine_loop_api.py
git commit -m "feat(api): PUT /jobs/cover-letters/{id}/final — store submitted text, edit distance, voice sample, fact candidates

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.5: Outcome service (status mapping, 14-day no-response, monotonic outcome, crediting won facts)

**Files:**
- Create: `/Users/admin/dev2/UpApply/api/app/services/outcomes.py`
- Create: `/Users/admin/dev2/UpApply/api/tests/test_outcomes.py`

**Interfaces:**
- Consumes: `credit_facts(db, fact_ids, won: bool)`; `CoverLetter.fact_ids_used`, `CoverLetter.final_text`; `Proposal.outcome`.
- Produces:
  - `NO_RESPONSE_AFTER = timedelta(days=14)`; `POSITIVE_OUTCOMES = frozenset({"replied", "interviewed", "hired"})`; `STATUS_TO_OUTCOME: dict[str, Optional[str]]`
  - `parse_submitted_at(value: Optional[str]) -> Optional[datetime]`
  - `resolve_outcome(raw_status: str, submitted_at: Optional[datetime], now: Optional[datetime] = None) -> Optional[str]`
  - `should_replace(current: Optional[str], new: Optional[str]) -> bool`
  - `async apply_outcome(db, proposal, outcome: Optional[str]) -> bool` (returns True when facts were credited)

- [ ] **Step 1: Write the failing test** `/Users/admin/dev2/UpApply/api/tests/test_outcomes.py`

```python
"""Pure tests for outcome mapping (no DB)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.outcomes import (
    NO_RESPONSE_AFTER,
    POSITIVE_OUTCOMES,
    parse_submitted_at,
    resolve_outcome,
    should_replace,
)

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("raw,expected", [
    ("responded", "replied"),       # extension list scraper: active_candidacies
    ("interviewed", "interviewed"),
    ("hired", "hired"),
    ("declined", "declined"),
    ("viewed", "viewed"),
    ("Replied", "replied"),
    ("no_response", "no_response"),
])
def test_status_maps_to_outcome(raw, expected):
    assert resolve_outcome(raw, NOW - timedelta(days=1), NOW) == expected


def test_submitted_is_no_signal_until_14_days():
    assert resolve_outcome("submitted", NOW - timedelta(days=13), NOW) is None
    assert resolve_outcome("submitted", NOW - NO_RESPONSE_AFTER, NOW) == "no_response"
    assert resolve_outcome("submitted", None, NOW) is None


def test_unknown_status_ignored_unless_stale():
    assert resolve_outcome("withdrawn-ish", NOW - timedelta(days=2), NOW) is None


def test_should_replace_is_monotonic():
    assert should_replace(None, "viewed")
    assert should_replace("no_response", "replied")
    assert should_replace("replied", "hired")
    assert not should_replace("hired", "replied")
    assert not should_replace("replied", "declined")
    assert not should_replace("viewed", None)
    assert not should_replace("hired", "hired")


def test_positive_outcomes():
    assert POSITIVE_OUTCOMES == {"replied", "interviewed", "hired"}


def test_parse_submitted_at():
    assert parse_submitted_at("Mar 3, 2026") == datetime(2026, 3, 3, tzinfo=timezone.utc)
    assert parse_submitted_at("2026-03-03T10:00:00+00:00") == datetime(2026, 3, 3, 10, tzinfo=timezone.utc)
    assert parse_submitted_at("yesterday") is None
    assert parse_submitted_at(None) is None
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_outcomes.py
```
Expected: FAIL (`ModuleNotFoundError: No module named 'app.services.outcomes'`).

- [ ] **Step 3: Implement** `/Users/admin/dev2/UpApply/api/app/services/outcomes.py`

```python
"""Outcome sync (spec §3.3): Upwork proposal statuses → voice-sample outcomes → fact credit.

Replaces learning_engine.winning_proposal_to_memory. A won letter credits the facts
it used (times_in_won), which feeds the evidence rerank win_signal.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cover_letter import CoverLetter
from app.models.proposal import Proposal
from app.services.facts import credit_facts

NO_RESPONSE_AFTER = timedelta(days=14)
POSITIVE_OUTCOMES = frozenset({"replied", "interviewed", "hired"})

# Raw status (extension scraper / client) → canonical outcome. None = no signal yet.
STATUS_TO_OUTCOME: dict[str, Optional[str]] = {
    "submitted": None,
    "viewed": "viewed",
    "responded": "replied",
    "replied": "replied",
    "interviewed": "interviewed",
    "hired": "hired",
    "declined": "declined",
    "no_response": "no_response",
}

# Outcomes only move forward; a reply is never overwritten by a later decline.
_RANK: dict[Optional[str], int] = {
    None: 0, "no_response": 1, "viewed": 2, "declined": 3,
    "replied": 4, "interviewed": 5, "hired": 6,
}


def parse_submitted_at(value: Optional[str]) -> Optional[datetime]:
    """Parse Upwork's 'Mar 3, 2026' or an ISO timestamp into an aware UTC datetime."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%b %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def resolve_outcome(
    raw_status: str, submitted_at: Optional[datetime], now: Optional[datetime] = None
) -> Optional[str]:
    """Map a raw status to an outcome; silent proposals older than 14 days → no_response."""
    outcome = STATUS_TO_OUTCOME.get(raw_status.strip().lower())
    if outcome is None and submitted_at is not None:
        now = now or datetime.now(timezone.utc)
        if now - submitted_at >= NO_RESPONSE_AFTER:
            return "no_response"
    return outcome


def should_replace(current: Optional[str], new: Optional[str]) -> bool:
    return new is not None and _RANK[new] > _RANK.get(current, 0)


async def apply_outcome(db: AsyncSession, proposal: Proposal, outcome: Optional[str]) -> bool:
    """Advance the proposal's outcome; credit facts on its first positive outcome.

    Returns True when facts were credited.
    """
    if not should_replace(proposal.outcome, outcome):
        return False
    was_positive = proposal.outcome in POSITIVE_OUTCOMES
    proposal.outcome = outcome
    if outcome in POSITIVE_OUTCOMES:
        proposal.client_responded = True
    if outcome == "hired":
        proposal.was_hired = True
    if was_positive or outcome not in POSITIVE_OUTCOMES or not proposal.job_id:
        return False

    letter = (await db.execute(
        select(CoverLetter)
        .where(CoverLetter.user_id == proposal.user_id, CoverLetter.job_id == proposal.job_id)
        .order_by(CoverLetter.final_text.is_(None), CoverLetter.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not letter or not letter.fact_ids_used:
        return False
    await credit_facts(db, list(letter.fact_ids_used), won=True)
    return True
```

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_outcomes.py
```
Expected: `12 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/services/outcomes.py api/tests/test_outcomes.py
git commit -m "feat(learning): outcome mapping service — 14-day no_response, monotonic outcomes, fact crediting

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.6: `POST /proposals/outcomes` bulk sync endpoint

**Files:**
- Modify: `/Users/admin/dev2/UpApply/api/app/schemas/proposal.py` (append at end)
- Modify: `/Users/admin/dev2/UpApply/api/app/api/v1/proposals.py` (imports lines 17–25; new endpoint inserted directly above `@router.get("/{proposal_id}", response_model=ProposalResponse)`, currently line 256; the existing-row branch of `import_proposals_from_upwork` as rewritten by Phase 1 Task 1.8)
- Create: `/Users/admin/dev2/UpApply/api/tests/test_proposal_outcomes_api.py`

**Interfaces:**
- Consumes: `resolve_outcome`, `apply_outcome`, `parse_submitted_at` (Task 3.5).
- Produces:
  - `ProposalOutcomeItem(upwork_proposal_id: Optional[str], proposal_id: Optional[str], job_title: Optional[str], status: str, submitted_at: Optional[str])`; `ProposalOutcomeSyncRequest(items: List[ProposalOutcomeItem])`; `ProposalOutcomeSyncResponse(updated: int, credited: int, not_found: int)`.
  - `POST /api/v1/proposals/outcomes`. Matching order: `proposal_id`, then `upwork_proposal_id`, then the newest proposal with the same `job_title` and no Upwork id, which then gets that Upwork id stamped on it. The title fallback links click-captured proposals, which have no Upwork id at submit time.
  - `POST /proposals/import-from-upwork` (Phase 1 Task 1.8) uses the same matcher, so a proposal-detail scrape links to the click-captured row instead of creating a duplicate voice sample with no `job_id` (which could never credit facts), and its outcome goes through `apply_outcome` so it only moves forward and credits facts exactly once.

- [ ] **Step 1: Write the failing test** `/Users/admin/dev2/UpApply/api/tests/test_proposal_outcomes_api.py`

```python
"""API tests for POST /api/v1/proposals/outcomes (real DB, real credit_facts)."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.cover_letter import CoverLetter
from app.models.fact import Fact
from app.models.job import Job
from app.models.proposal import Proposal
from tests.conftest import TestSessionLocal

URL = "/api/v1/proposals/outcomes"


async def _uid(client: AsyncClient, headers: dict) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


async def _seed(user_id: str, *, upwork_id: str | None, title: str, days_ago: int = 2,
                with_fact: bool = True) -> dict:
    async with TestSessionLocal() as s:
        job = Job(user_id=user_id, upwork_url=f"https://www.upwork.com/jobs/~{title[:4]}",
                  title=title, description="desc", skills_required=[])
        s.add(job)
        await s.flush()
        fact_ids = []
        if with_fact:
            fact = Fact(user_id=user_id, kind="project", statement=f"Fact for {title}", detail=None,
                        skills=[], industries=[], job_types=["cloud"], strength=0.8,
                        status="approved", source_type="bio_memory", sources=[],
                        times_used=1, times_in_won=0, embedding=[0.1] * 1536)
            s.add(fact)
            await s.flush()
            fact_ids = [fact.id]
        s.add(CoverLetter(user_id=user_id, job_id=job.id, content="draft", model_used="m",
                          fact_ids_used=fact_ids, final_text="final"))
        prop = Proposal(user_id=user_id, job_id=job.id, upwork_proposal_id=upwork_id,
                        cover_letter_text="final", job_title=title, source="extension",
                        author="chris_edited_ai",
                        submitted_at=datetime.now(timezone.utc) - timedelta(days=days_ago))
        s.add(prop)
        await s.commit()
        return {"proposal_id": prop.id, "fact_id": fact_ids[0] if fact_ids else None}


async def _prop(pid: str) -> Proposal:
    async with TestSessionLocal() as s:
        return (await s.execute(select(Proposal).where(Proposal.id == pid))).scalar_one()


async def _times_in_won(fid) -> int:
    async with TestSessionLocal() as s:
        return (await s.execute(select(Fact.times_in_won).where(Fact.id == fid))).scalar_one()


@pytest.mark.asyncio
async def test_reply_credits_facts_once(client, auth_headers):
    uid = await _uid(client, auth_headers)
    seeded = await _seed(uid, upwork_id="111", title="Azure SQL migration lead")

    r = await client.post(URL, headers=auth_headers,
                          json={"items": [{"upwork_proposal_id": "111", "status": "responded"}]})
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 1, "credited": 1, "not_found": 0}
    prop = await _prop(seeded["proposal_id"])
    assert prop.outcome == "replied" and prop.client_responded is True
    assert await _times_in_won(seeded["fact_id"]) == 1

    # Same status again: no change, no double credit. Upgrade to hired: outcome moves, still no double credit.
    r = await client.post(URL, headers=auth_headers,
                          json={"items": [{"upwork_proposal_id": "111", "status": "responded"}]})
    assert r.json() == {"updated": 0, "credited": 0, "not_found": 0}
    r = await client.post(URL, headers=auth_headers,
                          json={"items": [{"upwork_proposal_id": "111", "status": "hired"}]})
    assert r.json() == {"updated": 1, "credited": 0, "not_found": 0}
    prop = await _prop(seeded["proposal_id"])
    assert prop.outcome == "hired" and prop.was_hired is True
    assert await _times_in_won(seeded["fact_id"]) == 1


@pytest.mark.asyncio
async def test_title_fallback_stamps_upwork_id(client, auth_headers):
    uid = await _uid(client, auth_headers)
    seeded = await _seed(uid, upwork_id=None, title="Build a Next.js dashboard")
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"upwork_proposal_id": "222", "job_title": "Build a Next.js dashboard", "status": "interviewed"},
    ]})
    assert r.json() == {"updated": 1, "credited": 1, "not_found": 0}
    prop = await _prop(seeded["proposal_id"])
    assert prop.upwork_proposal_id == "222" and prop.outcome == "interviewed"


@pytest.mark.asyncio
async def test_stale_submitted_becomes_no_response_without_credit(client, auth_headers):
    uid = await _uid(client, auth_headers)
    stale = await _seed(uid, upwork_id="333", title="Old job", days_ago=20)
    fresh = await _seed(uid, upwork_id="444", title="New job", days_ago=3)
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"upwork_proposal_id": "333", "status": "submitted"},
        {"upwork_proposal_id": "444", "status": "submitted"},
        {"upwork_proposal_id": "999", "status": "responded"},
    ]})
    assert r.json() == {"updated": 1, "credited": 0, "not_found": 1}
    assert (await _prop(stale["proposal_id"])).outcome == "no_response"
    assert (await _prop(fresh["proposal_id"])).outcome is None
    assert await _times_in_won(stale["fact_id"]) == 0


@pytest.mark.asyncio
async def test_by_internal_id_and_other_users_isolated(client, auth_headers):
    uid = await _uid(client, auth_headers)
    seeded = await _seed(uid, upwork_id=None, title="Direct id", with_fact=False)
    r = await client.post(URL, headers=auth_headers, json={"items": [
        {"proposal_id": seeded["proposal_id"], "status": "viewed"},
    ]})
    assert r.json() == {"updated": 1, "credited": 0, "not_found": 0}

    other = await client.post("/api/v1/auth/register",
                              json={"email": "other@example.com", "password": "testpass123"})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    r = await client.post(URL, headers=other_headers, json={"items": [
        {"proposal_id": seeded["proposal_id"], "status": "hired"},
    ]})
    assert r.json() == {"updated": 0, "credited": 0, "not_found": 1}
    assert (await _prop(seeded["proposal_id"])).outcome == "viewed"


@pytest.mark.asyncio
async def test_requires_auth(client):
    r = await client.post(URL, json={"items": []})
    assert r.status_code in (401, 403)
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_proposal_outcomes_api.py
```
Expected: FAIL (405 Method Not Allowed on `POST /api/v1/proposals/outcomes`).

- [ ] **Step 3: Add the schemas** by appending to `/Users/admin/dev2/UpApply/api/app/schemas/proposal.py`:

```python
class ProposalOutcomeItem(BaseModel):
    """One proposal status seen on Upwork's Proposals page."""

    upwork_proposal_id: Optional[str] = None
    proposal_id: Optional[str] = None
    job_title: Optional[str] = None  # fallback match for click-captured proposals
    status: str  # submitted | viewed | responded | replied | interviewed | hired | declined | no_response
    submitted_at: Optional[str] = None  # "Mar 3, 2026" or ISO


class ProposalOutcomeSyncRequest(BaseModel):
    items: List[ProposalOutcomeItem]


class ProposalOutcomeSyncResponse(BaseModel):
    updated: int
    credited: int
    not_found: int
```

- [ ] **Step 4: Implement the endpoint** in `/Users/admin/dev2/UpApply/api/app/api/v1/proposals.py`

In the `from app.schemas.proposal import (` list, add after `ProposalImportFromUpwork,`:
```python
    ProposalOutcomeItem,
    ProposalOutcomeSyncRequest,
    ProposalOutcomeSyncResponse,
```
Replace the line `router = APIRouter()` with:
```python
from app.services.outcomes import apply_outcome, parse_submitted_at, resolve_outcome

router = APIRouter()
```
Insert directly above `@router.get("/{proposal_id}", response_model=ProposalResponse)`:
```python
async def _find_proposal_for_outcome(
    db: AsyncSession, user_id: str, item: ProposalOutcomeItem
) -> Optional[Proposal]:
    """Match by internal id, then Upwork id, then the newest same-title click-captured proposal lacking an Upwork id."""
    if item.proposal_id:
        return (await db.execute(
            select(Proposal).where(Proposal.id == item.proposal_id, Proposal.user_id == user_id)
        )).scalar_one_or_none()
    if not item.upwork_proposal_id:
        return None
    prop = (await db.execute(
        select(Proposal).where(
            Proposal.upwork_proposal_id == item.upwork_proposal_id,
            Proposal.user_id == user_id,
        )
    )).scalar_one_or_none()
    if prop or not item.job_title:
        return prop
    return (await db.execute(
        select(Proposal)
        .where(
            Proposal.user_id == user_id,
            Proposal.upwork_proposal_id.is_(None),
            Proposal.source == "extension",  # only click-captured rows (Task 3.4), never chatgpt_import
            Proposal.job_title == item.job_title,
        )
        .order_by(Proposal.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()


@router.post("/outcomes", response_model=ProposalOutcomeSyncResponse)
async def sync_proposal_outcomes(
    body: ProposalOutcomeSyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk status sync from the Proposals page → proposals.outcome; credit facts on wins."""
    updated = credited = not_found = 0
    for item in body.items:
        prop = await _find_proposal_for_outcome(db, current_user.id, item)
        if prop is None:
            not_found += 1
            continue
        if item.upwork_proposal_id and not prop.upwork_proposal_id:
            prop.upwork_proposal_id = item.upwork_proposal_id
        if prop.submitted_at is None:
            prop.submitted_at = parse_submitted_at(item.submitted_at)
        before = prop.outcome
        outcome = resolve_outcome(item.status, prop.submitted_at or prop.created_at)
        if await apply_outcome(db, prop, outcome):
            credited += 1
        if prop.outcome != before:
            updated += 1
    await db.commit()
    return ProposalOutcomeSyncResponse(updated=updated, credited=credited, not_found=not_found)
```

- [ ] **Step 4b: Route the proposal-detail import through the same matcher and `apply_outcome`.** In `import_proposals_from_upwork` (Phase 1 Task 1.8 version), replace:
```python
        if upwork_proposal_id:
            existing = (await db.execute(
                select(Proposal).where(
                    Proposal.upwork_proposal_id == upwork_proposal_id,
                    Proposal.user_id == current_user.id,
                )
            )).scalar_one_or_none()
            if existing:
```
with:
```python
        if upwork_proposal_id:
            # Upwork id first, then the newest click-captured row (Task 3.4) with the same title
            existing = await _find_proposal_for_outcome(
                db, current_user.id,
                ProposalOutcomeItem(upwork_proposal_id=upwork_proposal_id, job_title=job_title, status=status_str),
            )
            if existing:
                if not existing.upwork_proposal_id:
                    existing.upwork_proposal_id = upwork_proposal_id
```
and, in the same branch, replace:
```python
                if outcome:
                    existing.outcome = outcome
                continue
```
with:
```python
                if outcome:
                    await apply_outcome(db, existing, outcome)  # forward-only; credits facts once
                continue
```

Append this test to `/Users/admin/dev2/UpApply/api/tests/test_proposal_outcomes_api.py`:
```python


@pytest.mark.asyncio
async def test_detail_import_links_click_capture_and_credits_once(client, auth_headers):
    from unittest.mock import AsyncMock, patch

    uid = await _uid(client, auth_headers)
    seeded = await _seed(uid, upwork_id=None, title="Fabric data platform build")
    payload = {"proposals": [{
        "proposalId": "999", "jobTitle": "Fabric data platform build",
        "coverLetter": "final", "status": "Interviewing", "outcome": "interviewed",
    }]}
    with patch("app.api.v1.proposals.generate_embedding", AsyncMock(return_value=[0.1] * 1536)):
        r = await client.post("/api/v1/proposals/import-from-upwork", headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        r = await client.post("/api/v1/proposals/import-from-upwork", headers=auth_headers, json=payload)
    async with TestSessionLocal() as s:
        rows = (await s.execute(select(Proposal).where(Proposal.user_id == uid))).scalars().all()
    assert [p.id for p in rows] == [seeded["proposal_id"]]  # no duplicate voice sample
    assert rows[0].upwork_proposal_id == "999"
    assert rows[0].outcome == "interviewed"
    assert await _times_in_won(seeded["fact_id"]) == 1  # second import does not re-credit
```

- [ ] **Step 5: Run the tests and confirm they pass**

```bash
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q tests/test_proposal_outcomes_api.py tests/test_outcomes.py tests/test_proposals_import.py
```
Expected: all passed (18 in the first two files), 0 failed.

- [ ] **Step 6: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/app/schemas/proposal.py api/app/api/v1/proposals.py api/tests/test_proposal_outcomes_api.py
git commit -m "feat(api): POST /proposals/outcomes — bulk Upwork status sync, credits times_in_won on wins

import-from-upwork now links to click-captured rows and advances outcomes via apply_outcome.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.7: Retire `learning_engine.winning_proposal_to_memory`

**Files:**
- Modify: `/Users/admin/dev2/UpApply/api/agent/learning_engine.py` (docstring lines 1–8; imports lines 34 and 36; delete the "Mechanism 1" section, currently lines 56–98)
- Modify: `/Users/admin/dev2/UpApply/api/app/api/v1/job_queue.py` (import line 45; delete the "If hired" block, currently lines 769–779)
- Create: `/Users/admin/dev2/UpApply/api/tests/test_learning_engine_retired.py`
- Delete: `/Users/admin/dev2/UpApply/api/tests/test_learning_engine.py` (Phase 0 Task 0.5's two regression tests for the function this task removes)

**Interfaces:**
- Consumes: nothing new.
- Produces: `agent.learning_engine` no longer exports `winning_proposal_to_memory`. Wins credit facts through `POST /proposals/outcomes` instead (Task 3.6).

- [ ] **Step 1: Write the failing test** `/Users/admin/dev2/UpApply/api/tests/test_learning_engine_retired.py`

```python
"""The corpus-memory win path is retired in favour of fact crediting (spec §3.3)."""
import agent.learning_engine as learning_engine
import app.api.v1.job_queue as job_queue


def test_winning_proposal_to_memory_removed():
    assert not hasattr(learning_engine, "winning_proposal_to_memory")
    assert not hasattr(job_queue, "winning_proposal_to_memory")


def test_remaining_mechanisms_still_exported():
    assert callable(learning_engine.contribute_signal)
    assert callable(learning_engine.apply_cold_start)
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_learning_engine_retired.py
```
Expected: FAIL (`assert not True` on `hasattr(learning_engine, "winning_proposal_to_memory")`).

- [ ] **Step 3: Edit** `/Users/admin/dev2/UpApply/api/agent/learning_engine.py`

Replace the docstring paragraph
```python
1. WINNING PROPOSAL → MEMORY
   When a user is hired, the cover letter that won is added to their proposal
   corpus as a high-importance memory (importance=0.95). This improves future
   cover letter generation for this user.
```
with
```python
1. (Retired 2026-10) Winning proposals no longer become corpus memories.
   Wins now credit the facts a letter used via POST /api/v1/proposals/outcomes
   (app/services/outcomes.py), which feeds the evidence rerank win_signal.
```
Delete the two now-unused imports:
```python
from app.models.memory import Memory
```
```python
from app.core.embeddings import generate_embedding
```
Delete everything from the line `# ── Mechanism 1: Winning proposal → memory ────────────────────────────────────` up to (not including) the line `# ── Mechanism 2: Cross-user signal contribution ───────────────────────────────`. That removes the whole `async def winning_proposal_to_memory(...)` function, including any Phase 0 edits to its body.

- [ ] **Step 4: Edit** `/Users/admin/dev2/UpApply/api/app/api/v1/job_queue.py`

Change
```python
from agent.learning_engine import contribute_signal, winning_proposal_to_memory
```
to
```python
from agent.learning_engine import contribute_signal
```
Delete this block from `report_proposal_response` (it starts with the comment line, keeps the following `await db.flush()`, and uses the same 4-space indentation as the code around it):
```python
    # If hired: add winning cover letter to memory corpus
    if body.response_type == "invited" and item.draft_cover_letter:
        try:
            await winning_proposal_to_memory(
                user_id=current_user.id,
                job_title=item.title,
                job_description=item.description or "",
                cover_letter_text=item.draft_cover_letter,
                db=db,
            )
        except Exception as exc:
            logger.warning("winning_proposal_to_memory failed for item %s: %s", item_id, exc)

```

- [ ] **Step 5: Run the tests, plus a grep for leftovers, and confirm they pass**

```bash
cd /Users/admin/dev2/UpApply && git rm -q api/tests/test_learning_engine.py
cd /Users/admin/dev2/UpApply/api && ./venv/bin/pytest -q tests/test_learning_engine_retired.py && ! grep -rn "winning_proposal_to_memory" app agent tests
```
Expected: `2 passed`; grep prints nothing and exits 1, so the negated command succeeds.

- [ ] **Step 6: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add api/agent/learning_engine.py api/app/api/v1/job_queue.py api/tests/test_learning_engine_retired.py
# api/tests/test_learning_engine.py is already staged as deleted by the git rm above
git commit -m "refactor(learning): retire winning_proposal_to_memory; wins credit facts via /proposals/outcomes

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.8: Extension Vitest and the pure submit-capture field reader

**Files:**
- Modify: `/Users/admin/dev2/UpApply/extension/package.json` (`scripts` adds `"test"`; `devDependencies` gains `vitest` and `jsdom` through npm)
- Modify: `/Users/admin/dev2/UpApply/extension/package-lock.json` (npm)
- Create: `/Users/admin/dev2/UpApply/extension/vitest.config.ts`
- Create: `/Users/admin/dev2/UpApply/extension/src/content/__fixtures__/submit-proposal.html`
- Create: `/Users/admin/dev2/UpApply/extension/src/content/submit-capture.ts`
- Create: `/Users/admin/dev2/UpApply/extension/src/content/submit-capture.test.ts`

**Interfaces:**
- Consumes: `SELECTORS.coverLetterTextarea`, `SELECTORS.screeningQuestions`, `SELECTORS.screeningQuestionLabel`, `SELECTORS.screeningQuestionInput` (`src/content/upwork-selectors.ts`).
- Produces:
  - `export interface SubmittedAnswer { question: string; answer: string }`
  - `export interface CapturedSubmission { coverLetter: string | null; answers: SubmittedAnswer[] }`
  - `export function readSubmission(doc: Document): CapturedSubmission`
  - `export function isSubmitButton(target: Element | null): boolean`

The fixture is trimmed from `/Users/admin/dev2/UpApply/working/SubmitProposal.html` (the cover-letter `form-group`, the `.fe-proposal-job-questions.questions-area` with two questions, the `.fe-apply-footer-controls` footer) plus a nav search submit button as a negative case.

- [ ] **Step 1: Install the test tooling and add the script**

```bash
cd /Users/admin/dev2/UpApply/extension && npm install -D vitest@^2.1.9 jsdom@^25.0.1
```
In `/Users/admin/dev2/UpApply/extension/package.json` `scripts`, add after `"type-check": "tsc --noEmit"` (with a comma added to that line):
```json
    "test": "vitest run"
```
Create `/Users/admin/dev2/UpApply/extension/vitest.config.ts` (kept separate from `vite.config.ts` so the crx plugin does not load under test):
```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
  },
});
```

- [ ] **Step 2: Create the fixture** `/Users/admin/dev2/UpApply/extension/src/content/__fixtures__/submit-proposal.html`

```html
<!-- Trimmed from working/SubmitProposal.html (Upwork apply page, 2026-03). -->
<nav>
  <button type="submit" aria-label="Search" class="nav-btn-icon nav-search-btn">Search</button>
</nav>
<div class="fe-proposal-additional-details additional-details">
  <div class="air3-card air3-card-outline my-6x py-0">
    <header class="py-6x"><h2 class="mb-0 h4">Additional details</h2></header>
    <section class="air3-card-section air3-loader-container">
      <div class="cover-letter-area mt-6x mt-md-10x">
        <div class="form-group mb-8x">
          <label id="cover_letter_label" class="label"> Cover Letter </label>
          <div class="air3-textarea textarea-wrapper p-0">
            <textarea rows="10" placeholder="" aria-labelledby="cover_letter_label" class="air3-textarea inner-textarea"></textarea>
          </div>
        </div>
        <div class="cover-letter-info"><span class="cover-letter-CIS-detected-error"></span></div>
      </div>
      <div class="fe-proposal-job-questions questions-area">
        <div class="form-group mb-8x">
          <label id="" class="label"> Have you created or edited UI animations or micro-interactions before? If yes, please share examples or links to your work. </label>
          <div class="air3-textarea textarea-wrapper p-0">
            <textarea rows="10" placeholder="" aria-labelledby="" class="air3-textarea inner-textarea"></textarea>
          </div>
        </div>
        <div class="form-group mb-8x">
          <label id="" class="label"> When designing a responsive SaaS UI, how do you
            ensure the design works well across desktop, tablet, and mobile screens? </label>
          <div class="air3-textarea textarea-wrapper p-0">
            <textarea rows="10" placeholder="" aria-labelledby="" class="air3-textarea inner-textarea"></textarea>
          </div>
        </div>
      </div>
    </section>
  </div>
</div>
<footer class="pb-3x mt-6x">
  <div class="fe-apply-footer-controls" role="group">
    <button type="button" class="air3-btn air3-btn-primary m-0"> Send for 14 Connects <!----></button>
    <button type="button" class="air3-btn air3-btn-link m-0"> Cancel </button>
  </div>
</footer>
<div class="legacy">
  <button type="button" class="legacy-submit"><span>Submit Proposal</span></button>
</div>
```

- [ ] **Step 3: Write the failing test** `/Users/admin/dev2/UpApply/extension/src/content/submit-capture.test.ts`

```ts
import { describe, expect, it } from 'vitest';
import fixture from './__fixtures__/submit-proposal.html?raw';
import { isSubmitButton, readSubmission } from './submit-capture';

function loadFixture(): Document {
  return new DOMParser().parseFromString(fixture, 'text/html');
}

function setValue(doc: Document, selector: string, index: number, value: string): void {
  const el = doc.querySelectorAll<HTMLTextAreaElement>(selector)[index];
  el.value = value;
}

describe('readSubmission', () => {
  it('reads the cover letter and every screening answer at submit time', () => {
    const doc = loadFixture();
    setValue(doc, 'textarea[aria-labelledby="cover_letter_label"]', 0, '  Zero downtime is the whole job here.\n\nWarm regards,\nChris  ');
    setValue(doc, '.questions-area textarea', 0, 'Yes — Framer Motion work for a fintech dashboard.');
    setValue(doc, '.questions-area textarea', 1, 'Mobile-first breakpoints, tested on real devices.');

    const result = readSubmission(doc);

    expect(result.coverLetter).toBe('Zero downtime is the whole job here.\n\nWarm regards,\nChris');
    expect(result.answers).toEqual([
      {
        question: 'Have you created or edited UI animations or micro-interactions before? If yes, please share examples or links to your work.',
        answer: 'Yes — Framer Motion work for a fintech dashboard.',
      },
      {
        question: 'When designing a responsive SaaS UI, how do you ensure the design works well across desktop, tablet, and mobile screens?',
        answer: 'Mobile-first breakpoints, tested on real devices.',
      },
    ]);
  });

  it('does not double-count question groups matched by more than one selector', () => {
    const doc = loadFixture();
    expect(readSubmission(doc).answers).toHaveLength(2);
  });

  it('returns null cover letter when the textarea is empty or missing', () => {
    const doc = loadFixture();
    expect(readSubmission(doc).coverLetter).toBeNull();
    doc.querySelector('.cover-letter-area')?.remove();
    expect(readSubmission(doc).coverLetter).toBeNull();
  });

  it('returns no answers on a job without screening questions', () => {
    const doc = loadFixture();
    doc.querySelector('.questions-area')?.remove();
    expect(readSubmission(doc).answers).toEqual([]);
  });
});

describe('isSubmitButton', () => {
  it('accepts the apply footer primary button and clicks on its children', () => {
    const doc = loadFixture();
    const send = doc.querySelector('.fe-apply-footer-controls .air3-btn-primary');
    expect(isSubmitButton(send)).toBe(true);
    const inner = doc.createElement('span');
    send?.appendChild(inner);
    expect(isSubmitButton(inner)).toBe(true);
  });

  it('accepts a legacy "Submit Proposal" button by its label', () => {
    const doc = loadFixture();
    expect(isSubmitButton(doc.querySelector('.legacy-submit span'))).toBe(true);
  });

  it('rejects Cancel, the nav search submit, non-buttons and null', () => {
    const doc = loadFixture();
    expect(isSubmitButton(doc.querySelector('.fe-apply-footer-controls .air3-btn-link'))).toBe(false);
    expect(isSubmitButton(doc.querySelector('nav button'))).toBe(false);
    expect(isSubmitButton(doc.querySelector('textarea'))).toBe(false);
    expect(isSubmitButton(null)).toBe(false);
  });
});
```

- [ ] **Step 4: Run it and confirm it fails**

```bash
cd /Users/admin/dev2/UpApply/extension && npm test
```
Expected: FAIL (`Failed to resolve import "./submit-capture"`).

- [ ] **Step 5: Implement** `/Users/admin/dev2/UpApply/extension/src/content/submit-capture.ts`

```ts
/**
 * Pure field readers for capturing what was actually submitted on Upwork's
 * apply page (spec §3.2). No chrome.* or network access — wiring lives in index.ts.
 */
import { SELECTORS } from './upwork-selectors';

export interface SubmittedAnswer {
  question: string;
  answer: string;
}

export interface CapturedSubmission {
  coverLetter: string | null;
  answers: SubmittedAnswer[];
}

const SUBMIT_LABEL = /^(send for \d+ connects?|submit( a)? proposal)$/i;

function firstMatch(root: ParentNode, selectors: readonly string[]): Element | null {
  for (const selector of selectors) {
    if (selector.includes(':has-text')) continue;
    try {
      const el = root.querySelector(selector);
      if (el) return el;
    } catch {
      // invalid selector — try the next one
    }
  }
  return null;
}

function fieldValue(el: Element | null): string {
  if (!el) return '';
  const tag = el.tagName.toLowerCase();
  if (tag !== 'textarea' && tag !== 'input') return '';
  return (el as HTMLTextAreaElement | HTMLInputElement).value.trim();
}

function collapse(text: string | null | undefined): string {
  return (text ?? '').replace(/\s+/g, ' ').trim();
}

/** Read the cover letter and every screening answer from the apply form. */
export function readSubmission(doc: Document): CapturedSubmission {
  const coverLetter = fieldValue(firstMatch(doc, SELECTORS.coverLetterTextarea)) || null;

  const answers: SubmittedAnswer[] = [];
  // One combined selector list → each question group appears once even when it
  // carries both .fe-proposal-job-questions and .questions-area.
  doc.querySelectorAll(SELECTORS.screeningQuestions.join(', ')).forEach((group) => {
    const question = collapse(firstMatch(group, SELECTORS.screeningQuestionLabel)?.textContent);
    if (!question) return;
    answers.push({ question, answer: fieldValue(firstMatch(group, SELECTORS.screeningQuestionInput)) });
  });

  return { coverLetter, answers };
}

/** True when a click target is (inside) the proposal Submit / "Send for N Connects" button. */
export function isSubmitButton(target: Element | null): boolean {
  const button = target?.closest('button');
  if (!button) return false;
  if (button.closest('.fe-apply-footer-controls') && button.classList.contains('air3-btn-primary')) {
    return true;
  }
  return SUBMIT_LABEL.test(collapse(button.textContent));
}
```

- [ ] **Step 6: Run the tests and type-check, and confirm they pass**

```bash
cd /Users/admin/dev2/UpApply/extension && npm test && npm run type-check
```
Expected: `Test Files  1 passed (1)` / `Tests  7 passed (7)`; `tsc --noEmit` exits 0.

- [ ] **Step 7: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add extension/package.json extension/package-lock.json extension/vitest.config.ts \
  extension/src/content/__fixtures__/submit-proposal.html \
  extension/src/content/submit-capture.ts extension/src/content/submit-capture.test.ts
git commit -m "test(extension): add Vitest + jsdom; pure submit-capture field reader with fixture tests

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.9: Extension wiring for submit capture → `PUT /final`, and Proposals page → `POST /proposals/outcomes`

**Files:**
- Modify: `/Users/admin/dev2/UpApply/extension/src/lib/api-client.ts` (methods after `submitCoverLetter`, currently lines 279–284; types after `interface CoverLetter`, currently lines 891–903)
- Modify: `/Users/admin/dev2/UpApply/extension/src/background/index.ts` (imports lines 5–7; new cases directly above `case 'SCRAPE_JOB_CARDS':`, currently line 458)
- Modify: `/Users/admin/dev2/UpApply/extension/src/content/index.ts` (import line 15; new functions above `const INIT_FLAG`, currently line 800; `init()` body, currently lines 856–911)
- Modify: `/Users/admin/dev2/UpApply/extension/src/sidebar/pages/Generator.tsx` (store destructuring lines 11–29; new effect after the popup-editor listener effect, currently lines 101–110)

**Interfaces:**
- Consumes: `readSubmission`, `isSubmitButton` (Task 3.8); `extractProposals()` (`scrapers/proposals.ts`); `PUT /api/v1/jobs/cover-letters/{id}/final`; `POST /api/v1/proposals/outcomes`; `POST /api/v1/jobs/cover-letters/{id}/refine`.
- Produces:
  - `apiClient.refineCoverLetter(id: string, message: string, screeningAnswers?: QAPair[]): Promise<RefineResponse>`
  - `apiClient.submitFinal(id: string, finalText: string, finalAnswers: QAPair[]): Promise<FinalSubmitResponse>`
  - `apiClient.syncProposalOutcomes(items: ProposalOutcomeItem[]): Promise<ProposalOutcomeSyncResponse>`
  - Types `QAPair`, `RefineMessage`, `RefineResponse`, `FinalSubmitResponse`, `ProposalOutcomeItem`, `ProposalOutcomeSyncResponse`
  - Runtime messages `CAPTURE_SUBMISSION {data: {coverLetter, answers, pageUrl}}` and `SYNC_PROPOSAL_OUTCOMES {items}`, both handled in the background
  - `chrome.storage.local.activeDraft = {coverLetterId, jobUrl, timestamp}`, written by the Generator and valid for 24h. The draft is matched to the apply page by the job's `~slug`, the same way `pendingAutoFill` works today.

The extension has no test runner beyond Task 3.8's reader tests, so this task is verified with `type-check`, and the live behaviour is a human handoff.

- [ ] **Step 1: Write a failing type-level check.** Add the client calls in the background first (Step 3) and run `npm run type-check`. It fails because `submitFinal` and `syncProposalOutcomes` do not exist yet.

```bash
cd /Users/admin/dev2/UpApply/extension && npm run type-check
```
Expected (after Step 3 is applied before Step 2): FAIL `Property 'submitFinal' does not exist on type 'ApiClient'` and `Property 'syncProposalOutcomes' does not exist on type 'ApiClient'`.

- [ ] **Step 2: Add the API client methods and types** in `/Users/admin/dev2/UpApply/extension/src/lib/api-client.ts`

Directly after the `submitCoverLetter` method:
```ts
  async refineCoverLetter(id: string, message: string, screeningAnswers?: QAPair[]) {
    return this.request<RefineResponse>(`/api/v1/jobs/cover-letters/${id}/refine`, {
      method: 'POST',
      body: { message, screening_answers: screeningAnswers },
    });
  }

  async submitFinal(id: string, finalText: string, finalAnswers: QAPair[]) {
    return this.request<FinalSubmitResponse>(`/api/v1/jobs/cover-letters/${id}/final`, {
      method: 'PUT',
      body: { final_text: finalText, final_answers: finalAnswers },
    });
  }

  async syncProposalOutcomes(items: ProposalOutcomeItem[]) {
    return this.request<ProposalOutcomeSyncResponse>('/api/v1/proposals/outcomes', {
      method: 'POST',
      body: { items },
    });
  }
```
Directly after the closing `}` of `export interface CoverLetter { ... }`:
```ts
export interface QAPair {
  question: string;
  answer: string;
}

export interface RefineMessage {
  role: 'user' | 'assistant';
  content: string;
  screening_answers?: QAPair[];
  warnings?: string[];
  at: string;
}

export interface RefineResponse {
  cover_letter: string;
  screening_answers: QAPair[];
  warnings: string[];
  refine_messages: RefineMessage[];
}

export interface FinalSubmitResponse {
  id: string;
  edit_distance_pct: number;
  author: 'chris' | 'chris_edited_ai';
  proposal_id: string | null;
  fact_candidates: number;
}

export interface ProposalOutcomeItem {
  upwork_proposal_id?: string;
  proposal_id?: string;
  job_title?: string;
  status: string;
  submitted_at?: string;
}

export interface ProposalOutcomeSyncResponse {
  updated: number;
  credited: number;
  not_found: number;
}
```

- [ ] **Step 3: Add the background handlers** in `/Users/admin/dev2/UpApply/extension/src/background/index.ts`

After `import { logger } from '../lib/logger';` add:
```ts
import { apiClient } from '../lib/api-client';

// A generated draft stays linked to its job's apply page for a day (Submit-click capture).
const ACTIVE_DRAFT_TTL_MS = 24 * 60 * 60 * 1000;
```
Insert directly above `    case 'SCRAPE_JOB_CARDS':`:
```ts
    case 'CAPTURE_SUBMISSION': {
      // From the content script on Upwork's Submit click: { coverLetter, answers, pageUrl }.
      // Linked to the UpApply draft generated for the same job (~slug match).
      const { coverLetter, answers, pageUrl } = message.data ?? {};
      chrome.storage.local.get('activeDraft').then(async (stored) => {
        const draft = stored.activeDraft as
          | { coverLetterId: string; jobUrl: string; timestamp: number }
          | undefined;
        const pageSlug = String(pageUrl ?? '').match(/(~[a-zA-Z0-9]+)/)?.[1];
        const draftSlug = draft?.jobUrl?.match(/(~[a-zA-Z0-9]+)/)?.[1];
        if (
          !draft || !coverLetter || !pageSlug || pageSlug !== draftSlug ||
          Date.now() - draft.timestamp > ACTIVE_DRAFT_TTL_MS
        ) {
          // No UpApply draft for this job — the proposal-detail scraper backfills it later.
          try { sendResponse({ success: false, error: 'No matching UpApply draft' }); } catch { /* channel closed */ }
          return;
        }
        try {
          const result = await apiClient.submitFinal(draft.coverLetterId, coverLetter, answers ?? []);
          logger.log('UpApply: captured submission', result.author, 'edit distance', result.edit_distance_pct);
          try { sendResponse({ success: true, ...result }); } catch { /* channel closed */ }
        } catch (e) {
          try { sendResponse({ success: false, error: String(e) }); } catch { /* channel closed */ }
        }
      });
      return true; // async
    }

    case 'SYNC_PROPOSAL_OUTCOMES': {
      // From the content script when Chris opens Upwork's Proposals page.
      apiClient.syncProposalOutcomes(message.items ?? [])
        .then((result) => {
          logger.log('UpApply: outcome sync', result);
          try { sendResponse({ success: true, ...result }); } catch { /* channel closed */ }
        })
        .catch((e) => {
          try { sendResponse({ success: false, error: String(e) }); } catch { /* channel closed */ }
        });
      return true; // async
    }

```

- [ ] **Step 4: Wire the content script** in `/Users/admin/dev2/UpApply/extension/src/content/index.ts`

Change line 15 (as rewritten by Phase 1 Task 1.10, which replaced `scrapeProposalPageText` with `scrapeProposalDetail`)
```ts
import { extractAllProposals, scrapeProposalDetail } from './scrapers/proposals';
```
to
```ts
import { extractAllProposals, extractProposals, scrapeProposalDetail } from './scrapers/proposals';
import { isSubmitButton, readSubmission } from './submit-capture';
```
Insert directly above `const INIT_FLAG = '__upapply_initialized__';`:
```ts
/**
 * Capture what was actually submitted (spec §3.2): on the apply page's Submit
 * click, read the cover letter + screening answers and hand them to the background.
 */
function handleSubmitClick(event: MouseEvent): void {
  if (!window.location.href.includes('/apply')) return;
  if (!isSubmitButton(event.target as Element | null)) return;
  const submission = readSubmission(document);
  if (!submission.coverLetter) return;
  chrome.runtime.sendMessage({
    type: 'CAPTURE_SUBMISSION',
    data: { ...submission, pageUrl: window.location.href },
  }).catch(() => { /* background unavailable */ });
}

let lastOutcomeSyncUrl: string | null = null;

/**
 * Outcome sync (spec §3.3): when the Proposals page is opened, post the statuses
 * visible on the first page. No pagination clicks, no background polling.
 */
function syncProposalOutcomes(): void {
  if (!isMyProposalsPage()) return;
  const url = window.location.href;
  if (url === lastOutcomeSyncUrl) return;
  lastOutcomeSyncUrl = url;
  setTimeout(() => {
    const items = extractProposals().flatMap((p) =>
      p.proposalId && p.status
        ? [{
            upwork_proposal_id: p.proposalId,
            job_title: p.jobTitle ?? undefined,
            status: p.status,
            submitted_at: p.submittedAt ?? undefined,
          }]
        : []
    );
    if (items.length) {
      chrome.runtime.sendMessage({ type: 'SYNC_PROPOSAL_OUTCOMES', items }).catch(() => {});
    }
  }, 4000); // Upwork's list hydrates late (see extractAllProposals)
}

```
In `init()`, directly after the line `  initDraftSaver();` (the first one, before `// Watch for SPA navigation`), add:
```ts

  // Submit-click capture (capture phase so it runs before Upwork's own handlers)
  document.addEventListener('click', handleSubmitClick, true);

  // Outcome sync when landing directly on the Proposals page
  syncProposalOutcomes();
```
Inside the SPA-navigation observer, directly after the line `      checkPendingAutoFill().catch(() => {});`, add:
```ts

      // Outcome sync after SPA navigation to the Proposals page
      syncProposalOutcomes();
```

- [ ] **Step 5: Record the active draft in the Generator** (`/Users/admin/dev2/UpApply/extension/src/sidebar/pages/Generator.tsx`)

In the `useAppStore()` destructuring, add `coverLetterId,` on the line after `coverLetterError,`. Directly after the popup-editor `useEffect` (the one whose body checks `event.data?.type === 'COVER_LETTER_UPDATED'`), add:
```tsx
  // Link this draft to the job so the Upwork Submit-click capture can PUT /final
  useEffect(() => {
    if (!coverLetterId || !currentJob?.url) return;
    chrome.storage.local.set({
      activeDraft: { coverLetterId, jobUrl: currentJob.url, timestamp: Date.now() },
    });
  }, [coverLetterId, currentJob?.url]);
```

- [ ] **Step 6: Type-check and run the tests, and confirm they pass**

```bash
cd /Users/admin/dev2/UpApply/extension && npm run type-check && npm test
```
Expected: `tsc --noEmit` exits 0; `Tests  7 passed (7)`.

- [ ] **Step 7: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add extension/src/lib/api-client.ts extension/src/background/index.ts \
  extension/src/content/index.ts extension/src/sidebar/pages/Generator.tsx
git commit -m "feat(extension): capture Upwork Submit → PUT /final; Proposals page → POST /proposals/outcomes

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.10: Generator refine chat replaces Regenerate-with-feedback and Improve

**Files:**
- Create: `/Users/admin/dev2/UpApply/extension/src/sidebar/components/generator/RefineChat.tsx`
- Modify: `/Users/admin/dev2/UpApply/extension/src/sidebar/pages/Generator.tsx` (imports lines 1–8; destructuring line 23; state lines 44–57; handlers lines 122–201; JSX lines 497–532)
- Modify: `/Users/admin/dev2/UpApply/extension/src/sidebar/components/generator/CoverLetterPanel.tsx` (props lines 12–18, 29, 32, 49–55, 66, 69; JSX lines 162–192, 202–231)
- Modify: `/Users/admin/dev2/UpApply/extension/src/sidebar/store.ts` (interface line 63; implementation lines 309–330)
- Modify: `/Users/admin/dev2/UpApply/extension/src/lib/api-client.ts` (delete `regenerateCoverLetter` lines 272–277 and `improveCoverLetter` lines 286–293)

**Interfaces:**
- Consumes: `apiClient.refineCoverLetter`, `RefineMessage` (Task 3.9).
- Produces: `RefineChat` (default export) with props `{ messages: RefineMessage[]; warnings: string[]; sending: boolean; error: string | null; onSend: (message: string) => void }`. The `CoverLetterPanel` header now offers Edit, Copy and New draft; the feedback box, the Improve button and the improvement notes are removed.

The backend `/regenerate` and `/improve` endpoints stay in place for back-compat until the old path is removed (spec §4.3 step 6). Only the client calls go.

- [ ] **Step 1: Write a failing type-level check.** Delete `regenerateCoverLetter` and `improveCoverLetter` from `api-client.ts` (the Step 5 edit) first, then run type-check. It fails on the remaining callers.

```bash
cd /Users/admin/dev2/UpApply/extension && npm run type-check
```
Expected: FAIL `src/sidebar/store.ts: Property 'regenerateCoverLetter' does not exist on type 'ApiClient'` and `src/sidebar/pages/Generator.tsx: Property 'improveCoverLetter' does not exist on type 'ApiClient'`.

- [ ] **Step 2: Create** `/Users/admin/dev2/UpApply/extension/src/sidebar/components/generator/RefineChat.tsx`

```tsx
import { useState } from 'react';
import type { RefineMessage } from '../../../lib/api-client';

interface RefineChatProps {
  messages: RefineMessage[];
  warnings: string[];
  sending: boolean;
  error: string | null;
  onSend: (message: string) => void;
}

export default function RefineChat({ messages, warnings, sending, error, onSend }: RefineChatProps) {
  const [text, setText] = useState('');

  const send = () => {
    const message = text.trim();
    if (!message || sending) return;
    onSend(message);
    setText('');
  };

  return (
    <div className="card">
      <h4 className="font-medium text-gray-900 mb-2">Refine</h4>

      {messages.length > 0 && (
        <ul className="space-y-1 mb-2 text-xs max-h-[160px] overflow-auto">
          {messages.map((m, i) => (
            <li key={i} className={m.role === 'user' ? 'text-gray-800' : 'text-emerald-700'}>
              {m.role === 'user' ? `You: ${m.content}` : 'Draft updated'}
            </li>
          ))}
        </ul>
      )}

      {warnings.length > 0 && (
        <ul className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 space-y-1">
          {warnings.map((w, i) => (
            <li key={i} className="leading-snug">• {w}</li>
          ))}
        </ul>
      )}

      {error && <p className="text-xs text-red-600 mb-2">{error}</p>}

      <div className="flex gap-2">
        <input
          type="text"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder='e.g. "mention the Azure migration", "it was 160 servers", "shorter"'
          className="input text-sm flex-1"
          disabled={sending}
        />
        <button
          type="button"
          onClick={send}
          disabled={sending || !text.trim()}
          className="btn-primary text-sm disabled:opacity-50"
        >
          {sending ? 'Revising…' : 'Send'}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Edit** `/Users/admin/dev2/UpApply/extension/src/sidebar/components/generator/CoverLetterPanel.tsx`

In `interface CoverLetterPanelProps`, delete these lines:
```ts
  showFeedbackInput: boolean;
  feedbackText: string;
  setFeedbackText: (v: string) => void;
  improvementNotes: string[] | null;
  showImprovementNotes: boolean;
  setShowImprovementNotes: (v: boolean | ((prev: boolean) => boolean)) => void;
  improving: boolean;
```
```ts
  onRegenerate: () => void;
```
```ts
  onImprove: () => void;
```
In the destructured parameter list, delete:
```ts
  showFeedbackInput,
  feedbackText,
  setFeedbackText,
  improvementNotes,
  showImprovementNotes,
  setShowImprovementNotes,
  improving,
```
```ts
  onRegenerate,
```
```ts
  onImprove,
```
Replace the header buttons
```tsx
              <button type="button" onClick={onRegenerate} className="text-gray-500 hover:text-gray-700 text-sm">
                {showFeedbackInput ? 'Submit' : 'Regenerate'}
              </button>
              {showFeedbackInput && (
                <button type="button" onClick={onRegenerateFresh} className="text-gray-400 hover:text-gray-600 text-sm">
                  Fresh
                </button>
              )}
```
with
```tsx
              <button type="button" onClick={onRegenerateFresh} className="text-gray-500 hover:text-gray-700 text-sm" title="Generate a brand-new draft">
                New draft
              </button>
```
Delete the whole feedback-input block, from `          {showFeedbackInput && (` through its closing `          )}`, i.e. the block containing `placeholder="What should be different? (e.g., more technical, shorter...)"`.

Delete the whole improvement-notes block, from `          {improvementNotes && improvementNotes.length > 0 && (` through its closing `          )}`.

Replace the Improve + Mark Submitted row
```tsx
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={onImprove}
              disabled={improving}
              title="Compare against your won proposals and improve this letter"
              className="flex-1 btn-outline text-xs py-1.5 disabled:opacity-50"
            >
              {improving ? '✨ Comparing…' : '✨ Improve'}
            </button>
            <button
```
with
```tsx
          <div className="mt-2 flex gap-2">
            <button
```

- [ ] **Step 4: Edit** `/Users/admin/dev2/UpApply/extension/src/sidebar/pages/Generator.tsx`

Imports: change
```tsx
import { apiClient, ScreeningAnswerSearchResult, AttachmentData, MilestoneSuggestion } from '../../lib/api-client';
```
to
```tsx
import { apiClient, ScreeningAnswerSearchResult, AttachmentData, MilestoneSuggestion, RefineMessage } from '../../lib/api-client';
```
and add after `import MilestonesPanel from '../components/generator/MilestonesPanel';`:
```tsx
import RefineChat from '../components/generator/RefineChat';
```
In the `useAppStore()` destructuring, delete the line `    regenerateCoverLetter,`.

Replace
```tsx
  // Regeneration feedback state
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
```
with
```tsx
  // Refine thread state
  const [refineMessages, setRefineMessages] = useState<RefineMessage[]>([]);
  const [refineWarnings, setRefineWarnings] = useState<string[]>([]);
  const [refining, setRefining] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);
```
Replace
```tsx
  // Submit + improve feedback loop state
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [improving, setImproving] = useState(false);
  const [improvementNotes, setImprovementNotes] = useState<string[] | null>(null);
  const [showImprovementNotes, setShowImprovementNotes] = useState(false);
```
with
```tsx
  // Submit state
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
```
Replace `_resetFeedbackLoopState`, `handleRegenerate` and `handleRegenerateFresh` (from `  const _resetFeedbackLoopState = () => {` through the end of `handleRegenerateFresh`), keeping `handleGenerate` between them unchanged, so that the three become:
```tsx
  const _resetFeedbackLoopState = () => {
    setSubmitted(false);
    setRefineMessages([]);
    setRefineWarnings([]);
    setRefineError(null);
  };
```
```tsx
  const handleRegenerateFresh = () => {
    _resetFeedbackLoopState();
    generateCoverLetter(inclusions.trim() || undefined, prototypeUrl.trim() || undefined, includeCallOffer);
  };
```
(`handleRegenerate` is deleted entirely.)

Replace the whole `handleImprove` function (from `  const handleImprove = async () => {` through its closing `  };`) with:
```tsx
  const handleRefine = async (message: string) => {
    if (!coverLetterId) return;
    setRefining(true);
    setRefineError(null);
    const questions = currentJob?.screeningQuestions ?? [];
    const currentAnswers = questions
      .map((q, i) => ({ question: q.question, answer: questionAnswers[`q${i}`] ?? '' }))
      .filter(a => a.answer);
    try {
      const result = await apiClient.refineCoverLetter(coverLetterId, message, currentAnswers);
      useAppStore.getState().setCoverLetter(result.cover_letter);
      // The first draft's warnings (Phase 2 draftMeta) no longer apply; RefineChat shows the latest ones
      useAppStore.setState((s) => ({ draftMeta: s.draftMeta ? { ...s.draftMeta, warnings: [] } : null }));
      const revised: Record<string, string> = {};
      questions.forEach((q, i) => {
        const match = result.screening_answers.find(a => a.question.trim() === q.question.trim());
        if (match) revised[`q${i}`] = match.answer;
      });
      setQuestionAnswers(prev => ({ ...prev, ...revised }));
      setRefineMessages(result.refine_messages);
      setRefineWarnings(result.warnings);
      setSubmitted(false);
    } catch (err) {
      setRefineError(err instanceof Error ? err.message : 'Refine failed');
    } finally {
      setRefining(false);
    }
  };
```
In the `<CoverLetterPanel ... />` props, delete:
```tsx
              showFeedbackInput={showFeedbackInput}
              feedbackText={feedbackText}
              setFeedbackText={setFeedbackText}
              improvementNotes={improvementNotes}
              showImprovementNotes={showImprovementNotes}
              setShowImprovementNotes={setShowImprovementNotes}
              improving={improving}
```
```tsx
              onRegenerate={handleRegenerate}
```
```tsx
              onImprove={handleImprove}
```
Directly after the `<CoverLetterPanel ... />` element's closing `/>`, add:
```tsx

            {coverLetter && coverLetterId && (
              <RefineChat
                messages={refineMessages}
                warnings={refineWarnings}
                sending={refining}
                error={refineError}
                onSend={handleRefine}
              />
            )}
```

- [ ] **Step 5: Remove the dead client and store paths**

In `/Users/admin/dev2/UpApply/extension/src/lib/api-client.ts`, delete:
```ts
  async regenerateCoverLetter(id: string, feedback?: string, includeCallOffer: boolean = true) {
    return this.request<CoverLetter>(`/api/v1/jobs/cover-letters/${id}/regenerate`, {
      method: 'POST',
      body: { feedback, include_call_offer: includeCallOffer },
    });
  }

```
and
```ts
  async improveCoverLetter(id: string) {
    return this.request<{
      cover_letter_id: string;
      improved_content: string;
      improvement_notes: string[];
      hired_examples_used: number;
    }>(`/api/v1/jobs/cover-letters/${id}/improve`, { method: 'POST' });
  }

```
In `/Users/admin/dev2/UpApply/extension/src/sidebar/store.ts`, delete the interface line
```ts
  regenerateCoverLetter: (feedback?: string, includeCallOffer?: boolean) => Promise<void>;
```
and the implementation block from `  // Regenerate cover letter with optional feedback` through the closing `  },` of `regenerateCoverLetter` (the line before `  // Fill cover letter in page`).

- [ ] **Step 6: Type-check, test and confirm nothing is left behind**

```bash
cd /Users/admin/dev2/UpApply/extension && npm run type-check && npm test && ! grep -rn "regenerateCoverLetter\|improveCoverLetter\|showFeedbackInput\|improvementNotes" src
```
Expected: `tsc --noEmit` exits 0; `Tests  7 passed (7)`; grep prints nothing.

- [ ] **Step 7: Commit**

```bash
cd /Users/admin/dev2/UpApply
git add extension/src/sidebar/components/generator/RefineChat.tsx \
  extension/src/sidebar/components/generator/CoverLetterPanel.tsx \
  extension/src/sidebar/pages/Generator.tsx extension/src/sidebar/store.ts extension/src/lib/api-client.ts
git commit -m "feat(extension): refine chat in Generator replaces regenerate-with-feedback and Improve

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Phase 3 exit criteria

```bash
# API: full suite (baseline 191 + Phase 1–2 additions + Phase 3's 40 new tests), all green
cd /Users/admin/dev2/UpApply/api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q

# API: imports clean, single migration head
cd /Users/admin/dev2/UpApply/api && ./venv/bin/python -c "from app.main import app; print('OK')"
cd /Users/admin/dev2/UpApply/api && ./venv/bin/alembic heads   # → 024_refine_loop (head)

# Retired path is gone
cd /Users/admin/dev2/UpApply/api && ! grep -rn "winning_proposal_to_memory" app agent

# Extension: types + Vitest
cd /Users/admin/dev2/UpApply/extension && npm run type-check && npm test
```

---

## Human Handoffs

None of these are agent tasks. Each needs Chris, or an explicit go-ahead from him, because it touches prod, secrets, a shared remote or a live browser session. They are listed in the order they come up.

### Before or alongside Phase 0
1. **Rotate the UpApply login password for chris@servicevision.net.** The password is in pushed git history: commit `3b7affc`, file `docs/SESSION_CONTEXT_2026-03-11.md`, on `https://github.com/dbbuilder/UpApply`. Redacting the working tree does not remove it. Rewriting history with `git filter-repo` is optional and is Chris's call, because it rewrites the shared remote.
2. **Revoke the rotated-out OpenAI keys** at `https://platform.openai.com/api-keys`. Also decide whether to rotate the current `sk-proj-…` key, since its prefix appeared in a doc.
3. **Decide whether to track or gitignore** `scripts/import_upwork_html.py` and the `docs/SESSION_CONTEXT_*.md` files. Phase 0 leaves them untracked.
4. **Commit or stash the pre-existing extension version bump** in `extension/package.json`, `extension/package-lock.json` and `extension/public/manifest.json` before Phase 3. Task 3.8 edits `package.json` and `package-lock.json`.

### PRs and deploys (one stacked PR per phase, merged in order 0 → 1 → 2 → 3)
5. **Phase 0.** Open the PR `feat/mdg-0-bleeding` → `main`, merge it and let Render auto-deploy. Smoke-test in prod:
   - A screening answer generated with job context returns 200.
   - A queue item's "Generate draft" reaches `ready`.
   - A new cover letter's `model_used` shows the Claude model.

   Backfilling old `model_used` rows is optional.
6. **Phase 1.** Deploy. `start.sh` runs `alembic upgrade head`, which applies migration 022. Spot-check prod:
   - `SELECT count(*) FROM memories WHERE exclude_from_retrieval` returns about 800.
   - `SELECT author, count(*) FROM proposals GROUP BY 1` shows the new authors.

   Rows with `source='extension'` were re-tagged `chris_edited_ai`. If any of them are known to be unedited AI drafts, set `author='ai'` on them.
7. **Phase 2.** Deploy (migration 023), then rebuild the extension with `doppler run --project upapply --config prd -- npm run build` and reload `extension/dist`.
8. **Phase 3.** Deploy (migration 024) and confirm that `cover_letters` has `refine_messages`, `final_text`, `final_answers` and `edit_distance_pct`. Rebuild and reload the extension.

### Config and proxy
9. **Model env vars.**
   - Check `doppler secrets get COVER_LETTER_MODEL --project upapply --config prd`, and the same for `stg`. If either is pinned to `claude-sonnet-4-6`, the v2 writer silently runs on Sonnet. Delete it, or set it to `claude-opus-5-5`.
   - Optionally set `LEGACY_COVER_LETTER_MODEL`.
   - Sync with `./scripts/sync-doppler-to-render.sh`, using the `/render-env` skill. A Render env PUT replaces the whole set.
10. **Proxy pass-through (spec §2.4).** Before relying on v2, confirm that the AICostCentral `ANTHROPIC_BASE_URL` forwards the following:
    - `output_config`, both `format` and `effort`. The first real call that uses it is the Haiku fact extraction in step 13.
    - `tools` together with `output_config` in one request, plus the `tool_use` → `tool_result` round trip, which the Phase 3 refine needs.

    To check `structured_call` once, run this from `api/`:

    ```bash
    doppler run --project upapply --config prd -- ./venv/bin/python -c "import asyncio; from app.services.llm import structured_call; print(asyncio.run(structured_call(model='claude-opus-5-5', system='Reply as JSON.', user='Say hi', schema={'type':'object','properties':{'hi':{'type':'string'}},'required':['hi'],'additionalProperties':False}, effort='high', max_tokens=2000)))"
    ```

    Also confirm that the `llm … cache_read=` log line shows a value above 0 on a second v2 generation for the same user.

### Building the knowledge base (after Phase 1 is deployed)
11. **Fresh ChatGPT export.** Unzip it to `/Users/admin/dev2/UpApply/working/chatgpt-export/`, then check the counts with `api/venv/bin/python scripts/ingest_chatgpt_facts.py /Users/admin/dev2/UpApply/working/chatgpt-export --dry-run`.
12. **Seed facts and voice samples.**
    1. Go to Me → Facts and click "From bio memories" (these facts are auto-approved; skim them once).
    2. Re-scrape Upwork proposals with Sync → Import proposals. This needs a logged-in browser.
    3. Click "From Upwork proposals" until it reports 0 left.
    4. Run Sync → Import contracts if needed, then click "From Upwork contracts".
    5. Paste any client feedback worth keeping into "Add client feedback".
13. **ChatGPT ingestion against prod.** Start with `--limit 20`, then run the full export:

    ```bash
    UPAPPLY_PASSWORD='…' api/venv/bin/python scripts/ingest_chatgpt_facts.py /Users/admin/dev2/UpApply/working/chatgpt-export --email chris@servicevision.net
    ```

    This costs roughly one Haiku call per conversation.
14. **Review facts.** Work through the To review queue until about 80-200 facts are approved. Retrieval reads only approved facts.

### Evaluation and cut-over (after Phase 2 is deployed)
15. **Golden set.** Put 15-20 past jobs with Chris's actual submitted letters into `docs/evals/golden.json`, weighted toward ones that got replies. Run `scripts/eval_generation.py generate` against prod data. It costs about $0.10 per job and commits nothing.
16. **Blind eval.** Chris fills in `docs/evals/<date>/scores.csv` without opening `key.json`, then runs `score`. The pass bar is ≥ 75% new preferred, 0 unsupported claims and ≥ 2 facts cited per draft.
17. **Flip the flag, only on a pass.** Run this against prod Postgres. It changes one row.

    ```sql
    UPDATE user_profiles SET generation_v2 = true WHERE user_id = (SELECT id FROM users WHERE email = 'chris@servicevision.net');
    ```

    Then smoke-test on a live job page that has screening questions. "Facts used" and any warnings should show under the draft, and "Generate all" should fill the answers without separate per-question calls.

### Live loop checks (after Phase 3 is deployed)
18. **Submit capture.**
    1. On a real job, generate a draft and fill it in.
    2. Edit a few words in Upwork's textarea, answer the questions, and click "Send for N Connects".
    3. Confirm that `final_text`, `final_answers` and `edit_distance_pct` are set.
    4. Confirm that a `proposals` row exists with `author=chris_edited_ai`, `job_text` and `job_needs_embedding` filled.

    If nothing is captured, check the `.fe-apply-footer-controls` and `aria-labelledby="cover_letter_label"` selectors against the live DOM.
19. **Outcome sync.**
    1. Open `https://www.upwork.com/nx/proposals/` and look for `UpApply: outcome sync {updated, credited, not_found}` in the service-worker console.
    2. Spot-check one replied proposal: its `outcome` should be `replied`, and the facts its letter used should have `times_in_won` incremented.
20. **Refine quality and new candidates.**
    1. Try 3-5 refine nudges on real drafts, such as "mention the Azure migration", "it was 160 servers" or "shorter".
    2. Confirm that the cited facts are real and the verify warnings make sense.
    3. Review the new `refine_thread` and `upwork_submission` candidates in the Facts queue.

### Later (spec §4.3 step 6, after 2 weeks on v2; not in this plan)
21. **Retire the old path.** Write a follow-up plan that removes the legacy generation path, the corpus-memory retrieval code, `append_prototype_url`, the `/regenerate` and `/improve` endpoints, and the `gpt-4.1-nano` screening path. Nothing is deleted from the database.
