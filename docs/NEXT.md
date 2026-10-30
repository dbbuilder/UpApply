# NEXT — Memory-driven generation rebuild

autopilot: off
autopilot-max: 10
built: 2026-10-30T06:08
branch: main
head: 8a19f0e
status: active

<!--
Contract for unattended work in this repo. Read by advance-all, the autopilot Stop hook and dispatch-workstreams.
- autopilot: on  -> the Stop hook keeps the session working until every step below is ticked (capped at autopilot-max nudges per session).
- One step = one commit. Write "Done when" so a fresh session could verify it without asking.
-->

## Goal

v2 is live for Chris with job-queue drafts, canonical outcome stages, a results report, a new-user setup check, and the career-ops ideas 1-8 (graded requirements, client's-eye reviewer, client trust card, learned rules, skip reasons and filter audit). What is left unattended: document the newest tools in the runbook so the next attended session (and Gus's onboarding) can run them from it. Everything else waits on Chris (see Decisions pending).

## Guardrails

- No database migrations, deploys, secrets or env-var writes (see ~/.config/claude/overnight-defaults.md)
- Never push, open/merge PRs, call the production API, or touch the Render Postgres ipAllowList; commit locally only
- Never run a working-tree-wide discard (`git checkout -- .`, `git restore .`, `git reset --hard`, `git clean`, bare `git stash`); `git add` explicit paths only; never commit `working/` or `docs/evals/`
- Never flip `generation_v2` for anyone, never open `docs/evals/*/key.json`
- Voice rules live in the kit repo (`~/dev2/sv/writing-style`); change them only from Chris's dated feedback
- Tests: `docker start upapply-test-pg` (the container stops on its own; wait for `docker exec upapply-test-pg pg_isready -U upapply` before running), then `(cd api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q)` (938 passing at 8a19f0e). The test DB is shared with other sessions: on mass errors or deadlocks, create a private database in the same container (`CREATE DATABASE upapply_test_<name>` + `CREATE EXTENSION vector`), point TEST_DATABASE_URL at it, and drop it afterwards. A large skipped count means the DB was down. Extension: `cd extension && npx vitest run && npm run type-check`

## Steps

- [ ] 1. Runbook: add a "Reviewer, trust card, rules and filters" section to `docs/superpowers/runbook-memory-driven-generation.md` covering the opt-in client's-eye reviewer (`client_review` request flag / sidebar checkbox, what the verdicts do, cost and latency, never a second repair), the client trust card (tiers, which client fields the extension captures today, that it never changes the match score), learned rules (Me → Rules, propose/accept/reject, evidence = the user's own edits and refine requests, voice-kit users copy accepted rules to the kit's feedback log), and `scripts/filter_audit.py` (skip reasons, pre-filter rule names, the n<5 rule) — Done when: `grep -c 'client_review'`, `grep -c 'trust card'`, `grep -c 'learned-rules'` and `grep -c 'filter_audit'` on the runbook are each ≥ 1

## Decisions pending

- [2026-10-29] Gus Tello (gustello@gmail.com) has no UpApply account yet: he registers via the extension, then facts are loaded (his Upwork proposals or a ChatGPT export) and `GET /api/v1/profile/setup-status` shows ready before his flag goes on; voice kit optional (Chris / Gus)
- [2026-10-29] Re-run the Proposals import in the extension so the 144 'unknown' proposal stages (numeric Upwork codes) resolve; only code '7' is confirmed (Chris)
- [2026-10-29] Client feedback: 5 quotes from profile page 1 of 21 await approval in Me → Facts; paste the other pages (or expand the two shortened quotes) to import more (Chris)
- [2026-10-29] No v2 letters have been generated in real use yet, so the results report has nothing to compare; it fills in as Chris applies with the engine (Chris)
- [2026-10-30] Rebuild and reload the extension to get the client's-eye review checkbox, the trust card, the Rules tab and the skip-reason picker (Chris)
- [2026-10-30] Trust card coverage: proposals count, posted date and jobs posted are not extracted from Upwork job pages yet, and there is no client identifier for "applied to this client before"; needs one saved job page to confirm selectors (Chris to provide)
- [2026-10-29] Q11 A: the writer's direct Anthropic route needs a real `sk-ant-` key in Doppler `prd` as `WRITER_ANTHROPIC_API_KEY`; optional now that the proxy allows 300s (Chris)
- [2026-10-29] Q13: wire the voice kit into the gtm-bible sales agent next, then marketing (attended session)
- [2026-10-13] Q12: rotate the UpApply password (commit 3b7affc) and revoke the old Render key in git history (Chris)

## Log

- [2026-10-29] Deployed 6c33caa; migration 027 live; no v2 letters in real use yet
- [2026-10-29] step 1 done — cf9fe92 — GET /api/v1/profile/setup-status; 841 API tests pass with the DB
- [2026-10-29] step 2 done — 690604f — runbook §9 Measuring and feedback; 841 API tests pass with the DB
- [2026-10-29] #43 setup-status + runbook §9 merged; #44 review fixes: an unchanged AI draft is author 'ai' (never a voice sample), blank letters never count, setup-status creates nothing
- [2026-10-29] Relabel check: no proposals were labelled 'chris_edited_ai', nothing to fix
- [2026-10-30] #45 canonical skip reasons + scripts/filter_audit.py
- [2026-10-30] #46 client trust card (separate from the match score; failures never break analysis or the queue)
- [2026-10-30] #47 opt-in client's-eye reviewer (claude-sonnet-4-6; verdicts ride the single repair; never cuts the call offer or an explicit ask)
- [2026-10-30] #48 learned rules from the user's edits (migration 028, unique per user; Rules tab; accepted rules in writer and refine)
- [2026-10-30] Deployed 8a19f0e; migration 028 live with uq_learned_rules_user_rule; 938 API + 73 extension tests pass
