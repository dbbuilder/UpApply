# NEXT — Memory-driven generation rebuild

autopilot: off
autopilot-max: 10
built: 2026-10-29T00:00
branch: main
head: 9cbafd9
status: active

<!--
Contract for unattended work in this repo. Read by advance-all, the autopilot Stop hook and dispatch-workstreams.
- autopilot: on  -> the Stop hook keeps the session working until every step below is ticked (capped at autopilot-max nudges per session).
- One step = one commit. Write "Done when" so a fresh session could verify it without asking.
-->

## Goal

v2 is live for Chris (round 5 passed 17/20) and the proxy limit is fixed. Finish the rollout per `docs/ROLLOUT-STATUS-2026-10-28.md` §7: job-queue drafts on v2, a success report, then the legacy removal once every active user is on v2.

## Guardrails

- No database migrations, deploys, secrets or env-var writes (see ~/.config/claude/overnight-defaults.md)
- Never push, open/merge PRs, call the production API, or touch the Render Postgres ipAllowList; commit locally only
- Never run a working-tree-wide discard (`git checkout -- .`, `git restore .`, `git reset --hard`, `git clean`, bare `git stash`); `git add` explicit paths only; never commit `working/` or `docs/evals/`
- Never flip `generation_v2` for anyone, never open `docs/evals/*/key.json`
- Voice rules live in the kit repo (`~/dev2/sv/writing-style`); change them only from Chris's dated feedback
- Tests: `docker start upapply-test-pg`, then `(cd api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q)` (773 passing at 9cbafd9)

## Steps

- [ ] 1. Job-queue drafts on v2: in `api/app/api/v1/job_queue.py` (the `generate_cover_letter` call near line 401), use `generate_application` when the profile has `generation_v2` on, keeping legacy otherwise and storing the same draft fields — Done when: a new test shows a v2 user's queued job is drafted by `generate_application` and a flag-off user's by the legacy generator, and the full suite passes
- [ ] 2. Success report (Q4 A): `scripts/outcome_report.py` prints reply / interview / hire rates for proposals whose letter came from v2 (cover_letters with v2 traceability columns set) vs the 90 days before `generation_v2` was turned on, from the proposals + outcome_events tables, read-only — Done when: the script has a `--since` flag, a unit test over seeded rows passes, and `--help` documents both groups

## Decisions pending

- [2026-10-29] Q11 A needs a real `sk-ant-` key added to Doppler `prd` as `WRITER_ANTHROPIC_API_KEY` (UpApply holds only an AICostCentral virtual key); until then the writer uses the proxy, which now allows 300s (Chris)
- [2026-10-29] Q5: scraping client feedback needs one saved Upwork page that shows client feedback (contract or profile page source) to map the DOM (Chris to provide)
- [2026-10-29] Q3: Gus Tello next week needs his account email, approved facts (ChatGPT export or proposals) and, optionally, a `gus/` voice kit before his flag goes on (Chris)
- [2026-10-29] Q4: re-run the Proposals import in the extension (≥1.0.18) so outcomes arrive as readable statuses before the report means anything (Chris)
- [2026-10-13] Q12: rotate the UpApply password (commit 3b7affc) and revoke the old Render key in git history (Chris)
- [2026-10-29] Q13: wire the voice kit into the gtm-bible sales agent next, then marketing (attended session)

## Log

- [2026-10-28] Round 5 passed 17/20; generation_v2 on for Chris; A/B/C follow-up 2/3 to v2
- [2026-10-28] Kit v0.5.0 / #32: NDA "would be willing to sign", no live-or-die, one "happy" per close
- [2026-10-28] #33 call-offer wording check; #35 outcome credits the submitted letter; #34 closed (streaming cannot beat the proxy limit)
- [2026-10-29] AICostCentral #27 deployed: /v1/messages maxDuration 60 → 300; 97s and 113s calls verified
- [2026-10-29] 20 Vision Companies fact rewrites applied (Q1)
- [2026-10-29] Doppler made authoritative; full sync to Render (Q8)
- [2026-10-29] #36 extension 1.0.19 committed (Q9); checkout now on main
- [2026-10-29] Kit v0.5.1: experience-led openers note (Q10)
- [2026-10-29] #37 writer retry + optional direct Anthropic route (Q11 A+C)
