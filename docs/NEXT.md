# NEXT — Memory-driven generation rebuild

autopilot: off
autopilot-max: 10
built: 2026-10-29T05:08
branch: main
head: 6c33caa
status: active

<!--
Contract for unattended work in this repo. Read by advance-all, the autopilot Stop hook and dispatch-workstreams.
- autopilot: on  -> the Stop hook keeps the session working until every step below is ticked (capped at autopilot-max nudges per session).
- One step = one commit. Write "Done when" so a fresh session could verify it without asking.
-->

## Goal

v2 is live for Chris, job-queue drafts run on v2, outcomes map to canonical stages with a ledger, and a results report exists. Next: make onboarding a second user (Gus Tello) safe, and document the new measuring and client-feedback tools so the next attended session can run them from the runbook.

## Guardrails

- No database migrations, deploys, secrets or env-var writes (see ~/.config/claude/overnight-defaults.md)
- Never push, open/merge PRs, call the production API, or touch the Render Postgres ipAllowList; commit locally only
- Never run a working-tree-wide discard (`git checkout -- .`, `git restore .`, `git reset --hard`, `git clean`, bare `git stash`); `git add` explicit paths only; never commit `working/` or `docs/evals/`
- Never flip `generation_v2` for anyone, never open `docs/evals/*/key.json`
- Voice rules live in the kit repo (`~/dev2/sv/writing-style`); change them only from Chris's dated feedback
- Tests: `docker start upapply-test-pg`, then `(cd api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q)` (837 passing at 6c33caa). The test DB is shared with other sessions: if a run deadlocks or shows mass errors, rerun once before diagnosing

## Steps

- [x] 1. (cf9fe92) New-user setup check (career-ops idea 8): `GET /api/v1/profile/setup-status` returns `{ready: bool, approved_facts, voice_samples, has_profile_basics, missing: [..]}` for the current user, where ready needs at least 25 approved facts, at least 1 voice sample (a proposal written or edited by the user), and full_name + professional_title set; read-only, no new tables — Done when: tests cover a ready user, a brand-new user (every item listed in `missing`) and a user with facts but no voice samples, and the full suite passes
- [ ] 2. Runbook: add a "Measuring and feedback" section to `docs/superpowers/runbook-memory-driven-generation.md` covering `scripts/outcome_report.py` (groups, n<5 rule, pending/unknown, `--since`), the stage map in `app/services/proposal_status.py` (only confirmed Upwork codes, how to add one), `scripts/import_upwork_feedback.py` (copy a profile work-history page, dry run, write, review in Facts), and the new-user checklist (account, facts, setup-status, then the flag) — Done when: `grep -c 'outcome_report'`, `grep -c 'import_upwork_feedback'`, `grep -c 'proposal_status'` and `grep -c 'setup-status'` on the runbook are each ≥ 1

## Decisions pending

- [2026-10-29] Gus Tello (gustello@gmail.com) has no UpApply account yet: he registers via the extension, then facts are loaded (his Upwork proposals or a ChatGPT export) before his flag goes on; voice kit optional (Chris / Gus)
- [2026-10-29] Re-run the Proposals import in the extension so the 144 'unknown' proposal stages (numeric Upwork codes) resolve; only code '7' is confirmed (Chris)
- [2026-10-29] Client feedback: 5 quotes from profile page 1 of 21 are candidates awaiting approval in Me → Facts; paste the other pages (or expand the two shortened quotes) to import more (Chris)
- [2026-10-29] No v2 letters have been generated in real use yet, so the results report has nothing to compare; it fills in as Chris applies with the engine (Chris)
- [2026-10-29] Q11 A: the writer's direct Anthropic route needs a real `sk-ant-` key in Doppler `prd` as `WRITER_ANTHROPIC_API_KEY`; optional now that the proxy allows 300s (Chris)
- [2026-10-29] Q13: wire the voice kit into the gtm-bible sales agent next, then marketing (attended session)
- [2026-10-29] career-ops ideas not yet built: 4 outside "play the client" reviewer, 5 client legitimacy card, 6 learn rules from draft edits, 7 canonical skip reasons + pre-filter audit (Chris to prioritise)
- [2026-10-13] Q12: rotate the UpApply password (commit 3b7affc) and revoke the old Render key in git history (Chris)

## Log

- [2026-10-29] Kit v0.5.1: experience-led openers note (Q10)
- [2026-10-29] #37 writer retry + optional direct Anthropic route (Q11 A+C)
- [2026-10-29] #38 rollout status with Chris's decisions; runbook rounds 3-4 and CLAUDE.md model defaults on main
- [2026-10-29] #39 job-queue drafts on v2 with a traceable CoverLetter; submit-edit records the sent text
- [2026-10-29] #40 client feedback importer (scripts/import_upwork_feedback.py); 5 candidates from profile page 1
- [2026-10-29] career-ops studied: 8 ideas ranked; 1-3 approved
- [2026-10-29] #41 graded client requirements in the brief; missing critical stated requirements trigger the repair; answers from evidence only
- [2026-10-29] #42 migration 027 canonical proposal stages + stage-change ledger; scripts/outcome_report.py (baseline 17 sent, 5.9% replied)
- [2026-10-29] Deployed 6c33caa; migration 027 live; no v2 letters in real use yet
- [2026-10-29] step 1 done — cf9fe92 — GET /api/v1/profile/setup-status (25 approved facts, 1 voice sample, name + title); 841 API tests pass with the DB
