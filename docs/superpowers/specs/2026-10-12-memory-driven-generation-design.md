# Memory-Driven Generation — Design Spec

**Status:** DRAFT — complete, awaiting review
**Date:** 2026-10-12
**Author:** Chris Therriault (with Claude)

---

## Goal

Make UpApply's cover letters and screening answers as specific and organic as the ChatGPT workflow that has been winning work — and then surpass it by learning from outcomes.

**The ChatGPT benchmark (confirmed):** a long-running context that already "knows" Chris; paste the job, a strong draft arrives on the first or second try. → **First-draft quality is the whole game.** Refinement is secondary.

**Success criteria**
- Every draft cites ≥2 concrete, verified specifics from Chris's history (project, number, client, outcome) that are *relevant to this job's actual needs*.
- No two drafts share the same skeleton; reads as Chris, not as a template.
- Screening answers draw on the same knowledge as letters.
- Every claim is traceable to a verified fact (no hallucinated credentials).
- What Chris actually submits flows back into the system automatically.

## Diagnosis (why output is generic today)

Ranked root causes, from the 2026-10-12 repo review:

1. **Portfolio slots are filled with strangers' job posts.** ~800 ChatGPT-corpus memories are stored as `"JOB POSTING:\n…\n\nPROPOSAL WRITTEN: …"` (`scripts/import_chatgpt_corpus.py:208-229`). A new job post embeds closest to old job posts, so these win the top-5 slots, then get truncated to 500 chars (`api/app/services/job_analysis.py:254`). The model's "PORTFOLIO / RELEVANT EXPERIENCE" is mostly another client's requirements. `importance_score` is never read, so the 9 curated bio memories rarely surface.
2. **Voice examples are ChatGPT's output, not Chris's.** Imported letters are AI text; declined letters are labelled "outcome unknown — learn from both" (`api/app/services/cover_letter.py:201-208`).
3. **Retrieval is shallow.** One raw-job-post embedding, top-5, no rerank; job-description↔letter-text asymmetric matching for proposals; hired-first ordering ignores relevance; `metrics` / `client_feedback` never selected.
4. **Rigid template.** Fixed arc, mandatory call-offer sentence, fixed length band, "Warm regards," on every letter — the sameness *is* the AI tell.
5. **Screening answers** run on `gpt-4.1-nano` with no memories; `request.` vs `body.` bug (`api/app/api/v1/screening_answers.py:296-300`) 500s whenever job context is sent.
6. **No learning loop.** Upwork-textarea edits never captured; `winning_proposal_to_memory` throws a swallowed TypeError (`api/agent/learning_engine.py:83-91`); queue auto-draft crashes on wrong kwargs (`api/app/api/v1/job_queue.py:381-389`).
7. **Regenerate drops memories; Improve forbids new facts** — neither can make a letter *more* specific.

## Decomposition

| # | Sub-project | Ships as |
|---|---|---|
| 0 | **Stop the bleeding** — 3 crash bugs, plaintext password in `scripts/import_upwork_html.py`, partial key in `docs/SESSION_CONTEXT_2026-06-18.md`, lost-letter mislabel, `model_used` logging | One small PR, ahead of everything |
| 1 | **Knowledge layer** (this doc, §1) | Spec → plan → PRs |
| 2 | **Generation engine** (§2) | Spec → plan → PRs |
| 3 | **Refine + learn loop** (§3, intentionally light) | Spec → plan → PRs |

Approach chosen: **B — Context engine + refine thread**, borrowing tool-use from the agentic option for the refine thread only.

---

## §1 Knowledge Layer — *UNDER REVIEW*

### 1.1 Two stores, never mixed

| | `facts` (new table) | `voice_samples` (repurposed `proposals`) |
|---|---|---|
| **Purpose** | *What* to say | *How* to say it |
| **Unit** | One atomic, verified claim | One complete piece of text Chris sent |
| **Example** | "Led a 160-server on-prem → Azure migration for [client]; consolidated distributed SQL estate." | A submitted Upwork cover letter + its outcome |
| **Sources** | 9 bio memories; **Chris's own turns** in the ChatGPT export; submitted Upwork letters; contract feedback (`contractdetails`) | Upwork proposal-detail pages (scraped); sidebar submit-capture (§3) |
| **Never contains** | Job postings; AI-authored prose | ChatGPT-authored letters; unedited AI drafts |

### 1.2 `facts` schema (sketch)

| Column | Notes |
|---|---|
| `id`, `user_id` | |
| `kind` | `project` · `metric` · `credential` · `client_quote` · `role` · `tech` · `outcome` |
| `statement` | One or two sentences, first-person-neutral, written to be quotable |
| `detail` | Optional longer context the generator may draw on |
| `skills[]`, `industries[]`, `job_types[]` | Job types reuse existing anchors: `cto` · `saas` · `sql` · `cloud` · `ai` · `fullstack` |
| `strength` | 0–1; how compelling (hard number / named client / outcome ranks high) |
| `status` | `candidate` · `approved` · `rejected` |
| `source_type`, `source_ref` | e.g. `chatgpt_user_turn` + conversation id; `upwork_proposal` + proposal id |
| `times_used`, `times_in_won` | Feeds §3 learning |
| `embedding` | Embeds `statement` + `detail` only |

`voice_samples` = existing `proposals` table plus: `author` (`chris` · `chris_edited_ai` · `ai`), `outcome` enum (`no_response` · `viewed` · `replied` · `interviewed` · `hired` · `declined`), `job_needs_embedding` (embedding of the *job*, so retrieval is job↔job, fixing the asymmetric match). Only `author != 'ai'` rows are eligible as voice examples.

### 1.3 Ingestion pipeline (one-time, re-runnable, idempotent)

1. **ChatGPT export** (fresh, re-run 2026-10-12) → for each conversation, keep **user turns** (Chris's corrections, facts, preferences) and the final assistant letter *only as context* for what was asserted. LLM extracts candidate facts; assistant text is never stored as voice.
2. **Upwork proposal details** → extend the existing extension scraper (`extension/src/content/scrapers/proposals.ts`) to open each proposal's detail page and capture full submitted letter + screening answers + status. → `voice_samples` (author=`chris` or `chris_edited_ai`) **and** fact candidates.
3. **Contracts / feedback** → client feedback text + earnings → `client_quote` / `outcome` facts.
4. **Existing 9 bio memories** → split into atomic facts, auto-approved.
5. **Dedupe** by embedding similarity (≥0.92 → merge, keep strongest wording, union sources).

### 1.4 Human-in-the-loop review

New sidebar page **Facts**: queue of `candidate` facts grouped by kind, each with its source snippet. Approve / edit / reject, bulk-approve. Only `approved` facts are retrievable. Expected steady state: ~80–200 approved facts. This review is the step that makes the knowledge trustworthy — it replaces the years of corrections embedded in the ChatGPT context.

### 1.5 Retirement of the old corpus

The ~800 corpus `memories` rows (`source = chatgpt corpus`, content starting `JOB POSTING:`) become **ingestion input only** and are excluded from retrieval (flag, not delete — reversible). ChatGPT-imported `proposals` rows are re-tagged `author='ai'`.

### 1.6 Unchanged

pgvector + `text-embedding-3-small`, auth, extension shell, existing `memories` API (kept for back-compat; facts become the primary generation source).

### 1.7 Ongoing fact intake (decided 2026-10-12)

After the initial load, new candidates (from each submitted letter, contract, or refine-thread correction) that match an existing **approved** fact at similarity ≥0.92 are **auto-approved and merged** (source appended; the approved wording and ranking fields are untouched). Non-matching candidates go to the Facts review queue. A candidate whose **figures differ** from its near-duplicate ("160 servers" vs an approved "120 servers") is never merged: it is kept as a separate candidate so the review queue surfaces the conflict. Client-sourced facts (client quotes, contract feedback) are never auto-approved.

---

## §2 Generation Engine — *UNDER REVIEW*

### 2.1 Pipeline (replaces `run_full_analysis` → `build_*_prompt` → `clean_cover_letter`)

```
job post + screening Qs
   │
   ▼
[1] JOB BRIEF  (cheap model, structured output)
   needs[]            – 3-6 concrete things the client must believe ("has migrated prod SQL to Azure without downtime")
   job_types[]        – multi-label: cto/saas/sql/cloud/ai/fullstack (replaces first-keyword-wins routing)
   client_signals     – technical depth, tone, what they're worried about, red flags
   mirror_phrases[]   – the client's own words worth echoing
   explicit_asks[]    – "start your reply with…", "include your GitHub", etc.
   questions[]        – screening questions, verbatim
   │
   ▼
[2] EVIDENCE RETRIEVAL  (no LLM)
   per need: embed need text → top-8 approved facts
   rerank:   0.55·similarity + 0.25·strength + 0.20·win_signal(times_in_won/times_used, smoothed)
   select:   4-8 facts total, ≥1 per need where available, de-duplicated across needs
   + always_include facts from proposal_anchors (credential floor)
   + 2-3 voice_samples by job↔job similarity, author∈{chris, chris_edited_ai}, outcome-weighted
   │
   ▼
[3] WRITE  (writing model, adaptive thinking, structured output)
   one call → { cover_letter, screening_answers[{question, answer}], fact_ids_used[] }
   letter + answers generated jointly so evidence is distributed, not repeated
   │
   ▼
[4] VERIFY  (deterministic + cheap model)
   deterministic: banned phrases, sentence-starts-with-"I", salutation, closing, length band, explicit_asks honoured
   claim check:   every number / client / named project in the output must map to a provided fact
   on failure:    one automatic repair pass with the violations listed; still failing → return draft + warnings to UI
```

### 2.2 Prompt redesign — principles over templates

- **Remove** the three fixed STRUCTURE templates and the mandatory arc. Replace with principles: lead with the client's problem in their words; prove fit with the selected facts; one concrete "here's how I'd start" move; close.
- **Voice samples become the primary style guide** ("write the way these read"), not a footnote. Because they're real Chris text, style rules shrink to the hard constraints below.
- **Hard constraints kept (Chris's rules):** no sentence starts with "I"; no salutation; ends with `Warm regards,` + `preferred_closing`; banned-phrase list.
- **Length is job-driven:** brief/terse post → ~150-250 words; complex/CTO post → up to ~450. Screening answers 2-5 sentences unless the question asks for more.
- **Call offer & prototype URL are woven in by the model** (when enabled), not appended as canned sentences (`append_prototype_url` retired).
- **No fact, no claim:** the prompt states that specifics may only come from the EVIDENCE block; the verify step enforces it.

### 2.3 Screening answers

Same engine, same evidence, same model as the letter (no more `gpt-4.1-nano`, no more memory-blind answers). The per-question "Generate" button runs steps 1-4 scoped to that question, reusing the cached brief. The `request.`/`body.` bug is fixed in sub-project 0 regardless.

### 2.4 Models & cost

| Step | Model | Notes |
|---|---|---|
| Job brief, claim check, fact extraction (§1.3) | `claude-haiku-4-5` ($1/$5 per MTok) | Structured output; small, fast |
| Write (letter + answers) + refine thread (§3) | **`claude-opus-5-5`** ($4/$20 per MTok) — decided 2026-10-12 | Thinking always on; `output_config.effort: "high"` set explicitly (5.5 defaults to `medium`) |
| Embeddings | `text-embedding-3-small` (unchanged) | |

- Rough per-application cost (≈8K input, ≈3K output incl. thinking): ≈ $0.09 on Opus 5.5, plus ≈ $0.01 for Haiku steps; less with caching.
- Model IDs live in config (`cover_letter_model`, new `extraction_model`) so they can be swapped without code changes.
- **Prompt caching:** system prompt (rules + profile + always-include facts) is stable per user → cached prefix; job-specific content follows the breakpoint.
- **Opus 5.5 API constraints:** `temperature` is rejected (current code passes `0.75` → must be removed); `thinking: {type: "disabled"}` and `budget_tokens` are rejected (omit `thinking`, control via effort); forced `tool_choice` (`any`/`tool`) is rejected → use structured outputs (`output_config.format`) for the write step and `tool_choice: auto` in the refine thread; no assistant prefill. Verify the AICostCentral proxy (`anthropic_base_url`) passes `output_config` through before cut-over.
- Fix `CoverLetter.model_used` to record the model that actually generated.

### 2.5 Traceability & storage

`cover_letters` gains `brief` (JSONB), `fact_ids_used[]`, `voice_sample_ids[]`, `verify_warnings[]`. This is what §3's learning loop scores against: a won letter credits the facts and voice samples it used.

### 2.6 Retired / replaced

`build_system_prompt` templates, first-keyword job-type routing, `append_prototype_url`, memory top-5/500-char truncation path for generation, `/screening-answers/generate` nano path, `improve` endpoint's "do not add facts" rule (Improve folds into §3 refine).

## §3 Refine + Learn Loop — *UNDER REVIEW* (intentionally light)

The first draft is the product (§2). This loop exists to (a) handle the occasional nudge well and (b) feed what Chris actually sends back into §1.

### 3.1 Refine thread

- Replaces the single "Regenerate with feedback" box and the separate Improve button with a small chat under the draft in the Generator page.
- Each turn re-sends the **same brief, evidence, voice samples and current draft** (cached prefix) plus the thread history — unlike today's regenerate, which drops all context.
- The model has one tool, `search_facts(query)`, over approved facts, so "mention the Azure work" pulls the real fact instead of inventing one. Verify (§2.1 step 4) runs on every revised draft.
- If Chris states a new fact in the thread ("it was 160 servers, not 120"), it becomes a fact candidate (auto-approved per §1.7 when it matches).
- Thread stored on the cover letter (`refine_messages` JSONB). Rate limit raised from 5/hr to 30/hr.

### 3.2 Capture what was actually submitted

- Content script listens for Upwork's proposal **Submit** click; reads the cover-letter textarea and every screening-answer field at that moment; posts to new `PUT /cover-letters/{id}/final` (`final_text`, `final_answers`, `edit_distance_pct`).
- That becomes a `voice_sample` with `author = chris_edited_ai` (or `chris` if no UpApply draft was used), plus fact candidates.
- Backstop: the proposal-detail scraper (§1.3) reconciles anything the click-capture missed.

### 3.3 Outcome sync

- Proposals scraper runs when Chris opens Upwork's Proposals page (no background polling) and maps statuses → `voice_samples.outcome` (`viewed` · `replied` · `interviewed` · `hired` · `declined` · `no_response` after 14 days).
- On the **first** positive outcome (`replied`/`interviewed`/`hired`) of a proposal: increment `times_in_won` once on each approved fact in `fact_ids_used` and boost the voice sample's weight. Crediting is one-time per proposal (`facts_credited_at`), so a proposal advancing replied → interviewed → hired, or a re-sync, never credits twice. This is what makes retrieval improve over time (§2.1 rerank `win_signal`).
- Replaces the broken `learning_engine.winning_proposal_to_memory` path.

### 3.4 Explicitly deferred (YAGNI)

Learned style profiles, A/B testing of letter variants, autonomous submission changes, the daily discovery cron. Revisit after 30 days of outcome data.

---

## §4 Testing & Rollout — *UNDER REVIEW*

### 4.1 Tests

- **Unit (pytest, `api/tests/`):** rerank scoring and per-need selection; deterministic verify rules; claim-check mapping (LLM mocked); brief/structured-output parsing; fact dedupe + auto-approve threshold; outcome → `times_in_won` crediting.
- **Regression for sub-project 0 bugs:** screening generate with job context; queue draft call signature; `model_used` value.
- **Extension:** add Vitest for the submit-capture field reader only (first extension test; no broader test harness in scope).

### 4.2 Golden-set evaluation (the real acceptance test)

- 15-20 past jobs where Chris's actual submitted letter is known (from the proposal-detail scraper), weighted toward ones that got replies.
- Generate with old pipeline and new pipeline; Chris reviews pairs **blind** (order randomised).
- **Pass:** new preferred in ≥75% of pairs; zero unsupported claims flagged by verify; every draft cites ≥2 job-relevant facts.
- Script lives in `scripts/eval_generation.py`; results saved to `docs/evals/`.

### 4.3 Rollout

1. **PR 0** — stop the bleeding (independent, first).
2. **§1** — schema + migration (013), ingestion scripts, Facts review page. Chris reviews candidate facts.
3. **§2** — engine behind per-user flag `generation_v2` (old path untouched while flag off).
4. **Golden-set eval** → if pass, flip flag on for Chris.
5. **§3** — refine thread, submit capture, outcome sync.
6. After 2 weeks on v2: remove old generation path and corpus-memory retrieval code.

Nothing is deleted from the database at any stage; corpus memories are flagged out of retrieval and ChatGPT proposals re-tagged `author='ai'`.
