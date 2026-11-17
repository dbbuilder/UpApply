# NEXT — Memory-driven generation rebuild

autopilot: off
autopilot-max: 10
built: 2026-11-04T05:50
branch: main
head: a0d6508
status: active

<!--
Contract for unattended work in this repo. Read by advance-all, the autopilot Stop hook and dispatch-workstreams.
- autopilot: on  -> the Stop hook keeps the session working until every step below is ticked (capped at autopilot-max nudges per session).
- One step = one commit. Write "Done when" so a fresh session could verify it without asking.
-->

## Goal

v2 is live for Chris with job-queue drafts, canonical outcome stages, a results report, a new-user setup check, and the career-ops ideas 1-8 (graded requirements, client's-eye reviewer, client trust card, learned rules, skip reasons and filter audit). Automatic job gathering works against live Upwork (#49–#62, 2026-11-02): 10 keyword searches, paging back to a lookback window, budgets read from the tiles, server pre-filter and scoring; 325 scanned jobs in the queue (93 suggested, 232 filtered). Nothing has gone past Pending yet (0 reviewed, 0 v2 letters). The open problem is the match score: scanned jobs carry no skills list, so the 30% rule score sits at 85–94 and every scanned job gets about +27 (0.7 × LLM grade + 27). Step 2 writes the plan for a per-dimension rubric; building it waits on Chris.

## Guardrails

- No database migrations, deploys, secrets or env-var writes (see ~/.config/claude/overnight-defaults.md)
- Never push, open/merge PRs, call the production API, or touch the Render Postgres ipAllowList; commit locally only
- Never run a working-tree-wide discard (`git checkout -- .`, `git restore .`, `git reset --hard`, `git clean`, bare `git stash`); `git add` explicit paths only; never commit `working/` or `docs/evals/`
- Never flip `generation_v2` for anyone, never open `docs/evals/*/key.json`
- Voice rules live in the kit repo (`~/dev2/sv/writing-style`); change them only from Chris's dated feedback
- Tests: `docker start upapply-test-pg` (the container stops on its own; wait for `docker exec upapply-test-pg pg_isready -U upapply` before running), then `(cd api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q)` (996 passing at a0d6508). The test DB is shared with other sessions: on mass errors or deadlocks, create a private database in the same container (`CREATE DATABASE upapply_test_<name>` + `CREATE EXTENSION vector`), point TEST_DATABASE_URL at it, and drop it afterwards. A large skipped count means the DB was down. Extension: `cd extension && npx vitest run && npm run type-check` (150 passing at a0d6508)

## Steps

- [x] 1. Runbook: add a "Reviewer, trust card, rules and filters" section to `docs/superpowers/runbook-memory-driven-generation.md` covering the opt-in client's-eye reviewer (`client_review` request flag / sidebar checkbox, what the verdicts do, cost and latency, never a second repair), the client trust card (tiers, which client fields the extension captures today, that it never changes the match score), learned rules (Me → Rules, propose/accept/reject, evidence = the user's own edits and refine requests, voice-kit users copy accepted rules to the kit's feedback log), and `scripts/filter_audit.py` (skip reasons, pre-filter rule names, the n<5 rule) — Done when: `grep -c 'client_review'`, `grep -c 'trust card'`, `grep -c 'learned-rules'` and `grep -c 'filter_audit'` on the runbook are each ≥ 1
- [ ] 2. Plan: write `docs/superpowers/plans/2026-11-04-job-fit-rubric.md` for replacing the scan score with a per-dimension rubric (role level, stack/domain, evidence from approved facts, engagement, competition/timing, red-flag caps), how it is measured against the stored scanned jobs and the proposals with traction, and the rollout (shadow scores first; whether a migration is needed) — Done when: the file exists and `grep -c 'Done when\|## '` on it is ≥ 6; no code changes

## Decisions pending

- [2026-10-29] Gus Tello (gustello@gmail.com) has no UpApply account yet: he registers via the extension, then facts are loaded (his Upwork proposals or a ChatGPT export) and `GET /api/v1/profile/setup-status` shows ready before his flag goes on; voice kit optional (Chris / Gus)
- [2026-10-29] Re-run the Proposals import in the extension so the 144 'unknown' proposal stages (numeric Upwork codes) resolve; only code '7' is confirmed (Chris)
- [2026-10-29] Client feedback: 5 quotes from profile page 1 of 21 await approval in Me → Facts; paste the other pages (or expand the two shortened quotes) to import more (Chris)
- [2026-10-29] No v2 letters have been generated in real use yet, so the results report has nothing to compare; it fills in as Chris applies with the engine (Chris)
- [2026-11-04] Rubric: build the per-dimension job-fit score once the step-2 plan is approved (Chris)
- [2026-11-04] Turn on scheduled scans (Agent tab or ☰ → Settings; every 3 h). No scan has run since 2026-11-02 23:00 UTC; suggestions expire 7 days after ingest (Chris)
- [2026-11-04] First end-to-end use: approve one scanned job and generate its v2 draft; the approve → draft → send path has never run on a scanned job (Chris)
- [2026-11-04] Weak searches: "product lead …" (2 of 17 suggested, avg 37.6, none 70+) and "technical due diligence …" (1 of 8, avg 39.5) — keep, reword or drop; sales/assistant noise is already caught by the minimums (1 of 29 reached Pending) (Chris)
- [2026-11-04] Reload the extension to 1.0.31 (Pending lists every suggestion) (Chris)
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
- [2026-11-02] #50 ingest endpoint + #49 automatic scan merged and deployed (6632238, 0989651); review fixes: 25 jobs per call (capped jobs were never re-scored), 120/hour, a rejected scrape fails one query, malformed input no longer fails a batch, Level 5 drafts claimed
- [2026-11-02] step 1 done in #52 (runbook section); #51 found from a captured Upwork challenge page that the block detector returned null
- [2026-11-02] #52 and #51 merged; extension 1.0.22 built. Chris's 23 imported saved searches (Upwork topic_ids whose labels the scan would have searched literally) deactivated and replaced by a 10-search suite (CTO, advisory, SaaS/MVP, product lead, AI, Claude/LLM, AI-built rescue, SQL Server, Azure/data); old ids kept in the session scratchpad, reversible by setting active=true
- [2026-11-02] First live scans: #53 waits out a self-clearing challenge; #55 empty-search diagnostics showed 10 JobTiles but 0 title links; #56 reads search-page tiles (link found by its /jobs/~0<id> href); 100 jobs → 44 suggestions on the first full run
- [2026-11-02] #57/#62 Agent tab shows every pending suggestion (it loaded the newest 50, then 200, items of any status); #54/#61 scan panel progress and stale-error fixes
- [2026-11-02] #58 ingest takes max_age_days; #59 paging by &page=N to the lookback window (auto 14 days until 2026-11-05, then 7), Settings page, budget/posted/proposals read from tile text, Pending sorted by score; Chris's minimums set to $80/hr and $1,000 (were $75 / $500)
- [2026-11-02] #60 over-long scraped text is clipped instead of 422-ing a batch; a rejected batch is skipped with its reason. Full 10-search run: 356 sent, 249 seen, 60 pre-filtered, 24 below threshold, 23 new; budgets on 176 of 241 new jobs
- [2026-11-04] Checked in production: one 422 (before #60), 16 accepted ingests, no scan since 2026-11-02 23:00 UTC; search-query stats recorded for all 10 searches; 0 items reviewed, 0 v2 letters
- [2026-11-05] Job-fit rubric shadow built (branch feat/job-fit-shadow): job_fit.py on claude-haiku-4-5, migration 029 score_breakdown, posted time stored in client_info; 1056 API tests pass; live Haiku smoke OK (CTO job 92.5, commission-only setter 21.2)
