# NEXT — Memory-driven generation rebuild

autopilot: off
autopilot-max: 10
built: 2026-10-17T23:43
branch: feat/mdg-3-loop
head: e993612
status: active

<!--
Contract for unattended work in this repo. Read by advance-all, the autopilot Stop hook and dispatch-workstreams.
- autopilot: on  -> the Stop hook keeps the session working until every step below is ticked (capped at autopilot-max nudges per session).
- One step = one commit. Write "Done when" so a fresh session could verify it without asking.
-->

## Goal

The rebuild is merged and live (PRs #8–#13; prod on migration 025, `generation_v2` off). What remains unattended is bringing the repo docs in line with what shipped, so the next human step (fact ingest → review → golden set → blind A/B → flag flip) is self-explanatory. Everything that touches prod or needs a judgement is under Decisions pending.

## Guardrails

- No database migrations, deploys, secrets or env-var writes (see ~/.config/claude/overnight-defaults.md)
- Never push, open/merge PRs or call the production API; commit locally on `feat/mdg-3-loop` only
- Never commit the uncommitted extension version bump (extension/package.json, package-lock.json, public/manifest.json) or anything under `working/` / `docs/evals/`
- Never run `scripts/ingest_chatgpt_facts.py` without `--dry-run`, flip `generation_v2`, or touch the prod DB
- Tests: `cd api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q` (620 passing at origin/main 247e0f3); `cd extension && npx vitest run && npm run type-check`

## Steps

- [x] 1. (e17339b) Bring `feat/mdg-3-loop` up to `origin/main` (`git merge --no-edit origin/main`; local HEAD e993612 lacks #13, and this NEXT.md commit means it cannot fast-forward) — Done when: `git merge-base --is-ancestor origin/main HEAD` exits 0 and `grep -c '^| 025' CLAUDE.md` returns 1
- [x] 2. (3f808d9) CLAUDE.md "Corpus & Memory Scripts": add rows for `ingest_chatgpt_facts.py` (work-only filter by default — cover letter in title or any message, plus career titles; `--all` to disable; `--dry-run`, `--limit`) and `eval_generation.py` (`build-golden`, blind A/B); fix "9 entries" → 14 for `chris_bio_memories.json` — Done when: `grep -c 'ingest_chatgpt_facts.py\|eval_generation.py' CLAUDE.md` ≥ 3, `grep -c '9 entries' CLAUDE.md` returns 0, and `python3 -c "import json;print(len(json.load(open('scripts/chris_bio_memories.json'))))"` matches the number stated
- [ ] 3. CLAUDE.md "Testing": add the real API test command (`TEST_DATABASE_URL=… ./venv/bin/pytest -q` against the `upapply-test-pg` container on port 55499) and `npx vitest run` for the extension — Done when: `grep -c 'TEST_DATABASE_URL' CLAUDE.md` ≥ 1 and `grep -c 'vitest' CLAUDE.md` ≥ 1, and the documented commands pass when run
- [ ] 4. Runbook ingest section: document the work-only default and `--all`, the current export numbers (1,266 of 5,148 conversations → 1,286 items), running with `doppler run --project upapply --config dev -- …` once `UPAPPLY_PASSWORD` is set, and that step 3 (bio relabel) is now done by migration 025 — Done when: `grep -c -- '--all' docs/superpowers/runbook-memory-driven-generation.md` ≥ 1 and `grep -c 'UPAPPLY_PASSWORD' docs/superpowers/runbook-memory-driven-generation.md` ≥ 1

## Decisions pending

- [2026-10-13] Rotate the UpApply password leaked in pushed commit 3b7affc and revoke old OpenAI keys (user action)
- [2026-10-16] Set `UPAPPLY_PASSWORD` in Doppler upapply/dev (`! doppler secrets set UPAPPLY_PASSWORD --project upapply --config dev`), then say "go": ingest loop = `/facts/from-memories` (confirms migration 025) → 50-conversation trial (review sample) → remaining work conversations → `/facts/from-proposals` (user action, then attended session)
- [2026-10-16] After ingest: review facts (user), `build-golden`, blind A/B ≥75%, then flip `generation_v2` (user action)
- [2026-10-16] Multi-user gaps, after Chris's A/B passes: (a) writing hard rules (no "I"-start, banned phrases, "Warm regards") are Chris's but apply to every user → per-user setting (needs a migration); (b) proposal `author` labels `chris`/`chris_edited_ai` are naming only (already user-scoped) → rename needs a data migration; (c) ChatGPT export ingest is a local script → in-app upload + background job for other users. Recommendation: design (c) first, it is the onboarding blocker
- [2026-10-17] Steps 1–4 above are local doc commits on `feat/mdg-3-loop`; getting them to main needs a push + PR (user's go-ahead)

## Log

- [2026-10-15] CodeRabbit re-review of #8 checked — no new findings; #8 all 4 checks pass
- [2026-10-16] #8 merged — aae9ca8
- [2026-10-16] #9 CodeRabbit fixes (guarded re-embed, SQL-bounded backfill, anthropic>=1.13) — 15eb8d2; merged — 1a1fd74; deployed ~100s, /facts/* live
- [2026-10-16] #10 merged — 83f043b
- [2026-10-16] #11 merged — 1058c54; deployed ~60s, /refine live
- [2026-10-16] #12 work-only ChatGPT ingest filter + no personal facts — 1ab4d6a; merged — e993612
- [2026-10-16] Prod DB refuses external connections, so bio relabel shipped as migration 025 — 5d3b55d; #13 merged — 247e0f3; 620 API tests pass
- [2026-10-16] Export unzipped to working/chatgpt-export/ (gitignored); dry run: 1,266 of 5,148 conversations → 1,286 items
- [2026-10-17] step 1 done — e17339b — branch merged with origin/main (247e0f3); test DB container was stopped, restarted; 620 API tests pass
- [2026-10-18] step 2 done — 3f808d9 — ingest/eval scripts in CLAUDE.md table, bio count 14; flags verified via --help; 620 API tests pass
