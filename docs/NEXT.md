# NEXT — Memory-driven generation rebuild

autopilot: off
autopilot-max: 10
built: 2026-10-14T06:07
branch: feat/mdg-3-loop
head: 7599806
status: done

<!--
Contract for unattended work in this repo. Read by advance-all, the autopilot Stop hook and dispatch-workstreams.
- autopilot: on  -> the Stop hook keeps the session working until every step below is ticked (capped at autopilot-max nudges per session).
- One step = one commit. Write "Done when" so a fresh session could verify it without asking.
-->

## Goal

Phases 0–3 of the memory-driven generation rebuild (facts + voice samples, Opus 5.5 engine behind `generation_v2`, refine/learn loop) are code-complete as stacked PRs #8 → #9 → #10 → #11. The only unattended work left is keeping repo docs in step with the new pipeline; everything else is a human handoff (see Decisions pending).

## Guardrails

- No database migrations, deploys, secrets or env-var writes (see ~/.config/claude/overnight-defaults.md)
- Never push, merge, retarget or close PRs #8–#11; commit locally on `feat/mdg-3-loop` only
- Never commit the uncommitted extension version bump (extension/package.json, package-lock.json, public/manifest.json) or anything under `working/` / `docs/evals/`
- Never flip `generation_v2`, run the bio relabel SQL, or call prod — those are in the runbook for the user
- Tests: `cd api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q` (614 passing at head 7599806); `cd extension && npx vitest run && npm run type-check`

## Steps

- [x] 1. (2ffc21d) Update CLAUDE.md "Database Migrations" table with rows 013–024 (one-line description each, taken from the `api/alembic/versions/*.py` docstrings) — Done when: `grep -c '^| 0' CLAUDE.md` returns 24 and each new row matches its migration file's docstring
- [x] 2. (33fad1f) Add a "Memory-driven generation (v2)" subsection to CLAUDE.md under "Cover Letter Generation": `generation_v2` flag, facts store vs voice samples, Opus 5.5 writer / Haiku 4.5 extraction, verify + repair (incl. ≥2 verified specifics), refine loop caps, untrusted-text rule (`app/services/untrusted.neutralise()`), and links to the spec, plan and runbook; mark the existing sonnet-4-6 pipeline as the legacy (flag-off) path — Done when: CLAUDE.md mentions `generation_v2`, `claude-opus-5-5`, `neutralise()` and `docs/superpowers/runbook-memory-driven-generation.md`, and every path it cites exists (`ls` each)

## Decisions pending

- [2026-10-13] Rotate the UpApply password leaked in pushed commit 3b7affc and revoke old OpenAI keys (user action)
- [2026-10-16] #8 merged (aae9ca8). #9 retargeted to main, CodeRabbit fixes pushed, CI green — merge #9, then retarget #10 → main, then #11 (user's go-ahead per PR). Note: retargeting alone does not trigger CI here (ci.yml has default pull_request types); push or close/reopen to run it
- [2026-10-13] Prod rollout per docs/superpowers/runbook-memory-driven-generation.md: deploy (migrations 022–024 via start.sh), bio relabel SQL, run scripts/ingest_chatgpt_facts.py (export already unzipped to working/chatgpt-export/: 5,148 conversations → 5,611 Haiku extraction items; needs #9 deployed first), scrape proposals, review facts, build-golden + blind A/B (≥75%) before flipping `generation_v2` (user action)
- [2026-10-15] CodeRabbit skipped #9–#11 (auto-review only runs on PRs into main). Either comment `@coderabbitai review` on each now (A), or let it review as each is retargeted to main during merge (B, recommended: no extra noise, same coverage)

## Log

- [2026-10-13] Phases 0–3 implemented, hardened, pushed as PRs #8–#11 — 7599806 — 614 API tests + 36 extension tests passing
- [2026-10-13] CodeRabbit follow-ups: numeric-conflict facts, status case, ≥2 specifics, spec text — 9bf76ae, 5ceaf2a, 31a3ab8, 7599806
- [2026-10-13] Deps fix `sqlalchemy[asyncio]` (greenlet) — 49e5bd7 — #8 CI green
- [2026-10-13] build-golden, prod runbook, gitignore working/ + docs/evals/ — 493fe32, 8f1a1ea, 25bf4cd
- [2026-10-14] step 1 done — 2ffc21d — migrations 013–024 added to CLAUDE.md; 614 API tests pass
- [2026-10-14] step 2 done — 33fad1f — v2 pipeline section in CLAUDE.md; legacy model setting corrected; 614 API tests pass
- [2026-10-15] CodeRabbit re-review of #8 checked — no new findings (check green, only the summary was refreshed); #8 all 4 checks pass
- [2026-10-16] #9 CodeRabbit: guarded letter re-embed, SQL-bounded backfill, anthropic>=1.13 — 15eb8d2; facts.py comment nitpick skipped (already correct); merged forward bd71642, 0840afc — 616 API tests pass
