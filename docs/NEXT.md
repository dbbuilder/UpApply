# NEXT — Memory-driven generation rebuild

autopilot: off
autopilot-max: 10
built: 2026-11-16T22:30
branch: main
head: b6ffe2c
status: active

<!--
Contract for unattended work in this repo. Read by advance-all, the autopilot Stop hook and dispatch-workstreams.
- autopilot: on  -> the Stop hook keeps the session working until every step below is ticked (capped at autopilot-max nudges per session).
- One step = one commit. Write "Done when" so a fresh session could verify it without asking.
-->

## Goal

v2 is live for Chris and he is applying with it: since 2026-11-11 production logged 6 cover-letter generations, 3 recorded applications and 20 job analyses (Render request logs, 2026-11-16). Shipped 2026-11-09 to 11-16 (extension 1.0.37, API b6ffe2c, migrations 029-031): the job-fit rubric in shadow (#64), saved Upwork jobs as a scoring signal and a working saved-jobs import (#65, #67, #68), unmet client must-haves capping the score (#69), per-job "Include in cover letter" and Cancel analysis (#70, #71), per-question screening-answer prompts read from the apply page (#72), the client total-spent fix (#73), voice kit v0.5.2 with "Regards,\nChris" (#74) and Find-tab details and filters (#75). The scan has not run since 2026-11-02 (no `job-queue/ingest` requests in the logs since 2026-11-11), so the rubric's shadow week has collected nothing and its eval cannot start.

## Guardrails

- No database migrations, deploys, secrets or env-var writes (see ~/.config/claude/overnight-defaults.md)
- Never push, open/merge PRs, call the production API, or touch the Render Postgres ipAllowList; commit locally only
- Never run a working-tree-wide discard (`git checkout -- .`, `git restore .`, `git reset --hard`, `git clean`, bare `git stash`); `git add` explicit paths only; never commit `working/` or `docs/evals/`
- Never flip `generation_v2` for anyone, never open `docs/evals/*/key.json`
- Voice rules live in the kit repo (`~/dev2/sv/writing-style`); change them only from Chris's dated feedback
- Tests: `docker start upapply-test-pg` (the container stops on its own; wait for `docker exec upapply-test-pg pg_isready -U upapply` before running), then `(cd api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q)` (1106 passing on the merged #72 branch, 2026-11-15; equal to main b6ffe2c apart from the version bump). The test DB is shared with other sessions: on mass errors or deadlocks, create a private database in the same container (`CREATE DATABASE upapply_test_<name>` + `CREATE EXTENSION vector`), point TEST_DATABASE_URL at it, and drop it afterwards. A large skipped count means the DB was down. Extension: `cd extension && npx vitest run && npm run type-check` (180 passing on the same run). The machine is shared: under load (load average 70+ seen 2026-11-16) the API suite can take over 10 minutes

## Steps

- [x] 1. Runbook: "Reviewer, trust card, rules and filters" section — done in #52
- [x] 2. Plan: `docs/superpowers/plans/2026-11-04-job-fit-rubric.md` — done in #63 (approved 2026-11-05; updated 2026-11-16 to the weights and decisions as built)
- [ ] 3. Job-fit eval (plan phase 1): `scripts/eval_job_fit.py`, read-only against production in an attended session, over the scanned jobs that carry a `job_queue.score_breakdown`; Chris labels 40 jobs apply / maybe / skip — Done when: the script runs and its report shows the current score and the rubric side by side for the labelled jobs. Blocked until scheduled scans have run for about a week

## Decisions pending

- [2026-11-04] Turn on scheduled scans (Agent tab or ☰ → Settings; every 3 h). Nothing reaches the queue or the rubric's shadow week until they run (Chris) — the cheapest unblock of the most work
- [2026-11-16] Merge #66 (Search Lab counts saved jobs, proposes searches for uncovered ones, whole-word matching): CI green, waiting on Chris
- [2026-11-16] Check the Screening Questions card on a live apply page with questions (shipped in 1.0.37, not yet seen live) (Chris)
- [2026-11-11] Remove the legacy cover-letter pipeline: the runbook's two weeks on v2 passed 2026-11-11, but Gus would start on the flag-off path; decide the order (Chris)
- [2026-11-11] Saved-jobs import read about 200 of about 2,960 saves (paging gives up after 3 s in a throttled background tab); widen it only if older saves are wanted as signal (Chris)
- [2026-10-29] Gus Tello (gustello@gmail.com) has no UpApply account yet: he registers via the extension, then facts are loaded and `GET /api/v1/profile/setup-status` shows ready before his flag goes on (Chris / Gus)
- [2026-10-29] Client feedback: 5 quotes from profile page 1 of 21 await approval in Me → Facts; paste the other pages to import more (Chris)
- [2026-11-04] Weak searches: "product lead …" and "technical due diligence …" — keep, reword or drop (Chris)
- [2026-10-29] Q11 A: optional `WRITER_ANTHROPIC_API_KEY` (a real `sk-ant-` key) in Doppler `prd` (Chris)
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
- [2026-11-05] Rubric plan approved (weights, competition counts, Haiku, migration 029); #63 review comments fixed in a8f021c
- [2026-11-11] #64 rubric in shadow (migration 029 ran 06:02 UTC) and #65 saved jobs in scoring merged and live; #67/#68 saved-jobs import (Upwork moved the page back to /nx/search/jobs/saved/; batches of 25): Chris's import stored 200 saves (158 recent in the Queue, 42 signal only)
- [2026-11-11] #69 unmet client must-haves cap the live score at 45 (migration 030 freelancer_location ran 19:52 UTC); CodeRabbit fixes d5df32f
- [2026-11-13] Chris's preferred_closing set to 'Regards,\nChris' in production; voice kit v0.5.2 (sv-writing-style#6)
- [2026-11-15] #70-#75 merged and deployed (live b6ffe2c, migration 031 ran 00:37 UTC, extension 1.0.37). #72 completed: screening questions were never read because the extension only extracted on /jobs/ URLs and they exist only on the apply page; an independent review found 3 defects (AI answers counted as the user's words, answers carried across jobs, prompts shown to flag-off users), all fixed before merge. #73: client spend read only from About the client
- [2026-11-16] Render logs since 2026-11-11: 6 cover letters, 3 applications, 20 analyses, no scan ingests

