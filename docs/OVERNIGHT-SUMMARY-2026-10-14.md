# Overnight summary — 2026-10-14

Branch `feat/mdg-3-loop` (local only, nothing pushed). Contract: `docs/NEXT.md`, now `status: done`.

## Done

| Step | Commit | Result |
|------|--------|--------|
| 1. CLAUDE.md migrations table 013–024 | 2ffc21d | 24 rows, each from its migration docstring |
| 2. CLAUDE.md v2 pipeline section | 33fad1f | `generation_v2` flag, facts vs voice samples, Opus 5.5 writer / Haiku 4.5 extraction, verify + single repair (≥2 specifics), refine caps, `neutralise()` rule, links to spec/plan/runbook; existing pipeline relabelled legacy |

Also fixed while writing step 2: CLAUDE.md said the legacy pipeline uses the `cover_letter_model` setting; it actually uses `legacy_cover_letter_model` (`cover_letter_model` is now the v2 Opus writer).

Verification: API suite 614 passed after each step. Docs-only changes, so the extension was not rebuilt.

## Blocked on you (unchanged)

- Rotate the UpApply password leaked in pushed commit 3b7affc; revoke old OpenAI keys
- Merge PRs #8 → #9 → #10 → #11 in order, retargeting each to main so CI runs
- Prod rollout per `docs/superpowers/runbook-memory-driven-generation.md`
- Triage CodeRabbit's re-review of #8 if it posted new comments

## Note

These docs commits sit on `feat/mdg-3-loop`, so the next push of that branch adds them (and `docs/NEXT.md`) to PR #11.
