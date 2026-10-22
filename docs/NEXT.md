# NEXT — Memory-driven generation rebuild

autopilot: off
autopilot-max: 10
built: 2026-10-21T06:05
branch: feat/mdg-3-loop
head: 64afe8a
status: active

<!--
Contract for unattended work in this repo. Read by advance-all, the autopilot Stop hook and dispatch-workstreams.
- autopilot: on  -> the Stop hook keeps the session working until every step below is ticked (capped at autopilot-max nudges per session).
- One step = one commit. Write "Done when" so a fresh session could verify it without asking.
-->

## Goal

The v2 engine is built, merged and live behind `generation_v2` (off). Facts are loaded (265 approved), the proposal history is scraped (194 / 166 complete) and the blind A/B packet is waiting on Chris's judgement. What is left unattended: make the docs match what actually shipped and stop the scraper storing Upwork's opaque numeric status codes, so outcomes can drive the learning loop.

## Guardrails

- No database migrations, deploys, secrets or env-var writes (see ~/.config/claude/overnight-defaults.md)
- Never push, open/merge PRs, call the production API, or touch the Render Postgres ipAllowList; commit locally on `feat/mdg-3-loop` only
- Never commit the uncommitted extension version bump (extension/package.json, package-lock.json, public/manifest.json) or anything under `working/` / `docs/evals/`
- Never flip `generation_v2`, never open or summarise `docs/evals/*/key.json` (the A/B answer key)
- Tests: `docker start upapply-test-pg`, then `cd api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q` (644 passing at 64afe8a; a large skipped count means the DB is down) and `cd extension && npx vitest run && npm run type-check` (56 passing)

## Steps

- [x] 1. (e7906d3) CLAUDE.md "Corpus & Memory Scripts": the `ingest_chatgpt_facts.py` row still says "Work-only by default"; since #15 the default is `--source signed` (final message signed "Chris"/"Chris Therriault" per conversation, sent as `chatgpt_signed_letter`), with `--source work` / `--source all` (`--all` alias) — Done when: `grep -c 'source signed' CLAUDE.md` ≥ 1, `grep -c 'Work-only by default' CLAUDE.md` returns 0, and `api/venv/bin/python scripts/ingest_chatgpt_facts.py --help` lists `--source`
- [x] 2. (5085137) Runbook (`docs/superpowers/runbook-memory-driven-generation.md`): record what the rollout actually needed — ingest default `--source signed`; proposal import pacing/chunks and that Upwork pages now carry `<script id="__NUXT_DATA__">` (Nuxt 3) instead of `window.__NUXT__`; `/facts/from-proposals` and `/facts/from-contracts`; build-golden/generate need prod DB access, done by temporarily setting the Render Postgres `ipAllowList` to this Mac's `/32` and clearing it afterwards — Done when: `grep -c '__NUXT_DATA__' docs/superpowers/runbook-memory-driven-generation.md` ≥ 1, `grep -c 'ipAllowList' docs/superpowers/runbook-memory-driven-generation.md` ≥ 1, `grep -c 'source signed' docs/superpowers/runbook-memory-driven-generation.md` ≥ 1
- [ ] 3. Extension: when recording a scraped proposal, prefer the list page's human-readable status text over the detail page's numeric Upwork code (`status: nuxtStatus || …` in `extension/src/background/index.ts`), keeping the numeric code only as a last resort, via a pure helper in `extension/src/lib/proposal-scrape.ts` — Done when: `npx vitest run` passes including a new test for the helper (list text wins; numeric code used only when no list text), and `npm run type-check` is clean

## Decisions pending

- [2026-10-13] Rotate the UpApply password (exposed in commit 3b7affc and in the 2026-10-19 session transcript); revoke the dead Render key still in git history (`rnd_wfmF…`, removed by #14) (user action)
- [2026-10-21] Judge the blind A/B at https://claude.ai/artifact/D6rGtxxbmnGPBDkihzFzQ9, then say "score the A/B": read `judgments` → fill `docs/evals/2026-10-20/scores.csv` → `eval_generation.py score`; ≥75% of decided pairs → flip `generation_v2` for Chris (user action, then attended session)
- [2026-10-21] Upwork numeric application status codes ('8' ×97, '2' ×44, '7' ×6, '3', '10') can't be mapped to outcomes yet — only '7' = active submitted is confirmed (saved page source). Needs a few proposal pages with known outcomes to map, or step 3's list-text status on a re-scrape (user to provide pages, or re-run the Proposals import after step 3 ships)
- [2026-10-21] Won Contracts import stores contract titles/dates but no client feedback text, so no `client_quote` facts exist; capturing feedback gives the strongest evidence type — design needed (A: scrape feedback on contract pages, B: paste testimonials manually as facts)
- [2026-10-21] `scripts/sync-doppler-to-render.sh` pushes every Doppler `prd` value; Doppler and Render had drifted (stale key, wrong `/v1` base URL) — decide the source of truth before the next sync (A: Doppler authoritative, fix it first; B: sync only named keys)
- [2026-10-21] Unused candidates in the queue: 1,722 from signed ChatGPT letters (pairs/weaker one-offs), 791 weaker proposal claims, 61 low-value, 22 contract records, 142 doubtful unsigned turns — keep (harmless, never reach a letter) or bulk-reject (recommendation: keep until the A/B passes)

## Log

- [2026-10-19] #15 facts from Chris-signed letters only + tighter extractor; #16 doubtful flag (migration 026); 129 approved after consolidation
- [2026-10-20] #17 'I' banned only as first word; extractor skips compensation; 9 compensation facts removed; one-offs 143→62; 198 approved
- [2026-10-20] #18 throttle-safe scraper (pacing, backoff, chunks, incremental save, skip complete)
- [2026-10-20] #19 scraper decodes Upwork's Nuxt 3 `__NUXT_DATA__` (window.__NUXT__ gone); 194 proposals, 166 complete
- [2026-10-20] #20 prod bug: anthropic SDK 1.13 rejects `temperature` → legacy cover letters crashed; moved to extra_body + AST guard test — 7b09267
- [2026-10-20] /facts/from-proposals: 1,362 candidates → 284 dup rejected → 69 shortlisted → 67 approved; 265 approved total
- [2026-10-20] Golden set (20 jobs) + blind A/B packet generated via temporary prod DB allowlist (removed after); judging page published
- [2026-10-21] /facts/from-contracts: 22 weak contract-record candidates, left unused; no client feedback captured
- [2026-10-21] step 1 done — e7906d3 — CLAUDE.md ingest row: default --source signed, work/all modes; --help lists --source; 644 API tests pass
- [2026-10-22] step 2 done — 5085137 — runbook: --source signed ingest, Nuxt 3 __NUXT_DATA__ scrape + pacing/chunks, from-proposals/contracts, temporary ipAllowList for build-golden/generate; 644 API tests pass
