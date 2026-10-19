# Overnight summary — 2026-10-18

Branch `feat/mdg-3-loop` (local only, nothing pushed). Contract: `docs/NEXT.md`, now `status: done`.

## Done

| Step | Commit | Result |
|------|--------|--------|
| 1. Branch up to origin/main | e17339b | Includes #13 (migration 025); 620 API tests pass |
| 2. CLAUDE.md scripts table | 3f808d9 | `ingest_chatgpt_facts.py` and `eval_generation.py` rows; bio memories 14 (was "9") |
| 3. CLAUDE.md Testing section | e281022 | Docker pgvector test DB, pytest with `TEST_DATABASE_URL`, vitest + type-check; all run as written |
| 4. Runbook ingest section | 87d5839 | Work-only default, `--all`, 1,266 of 5,148 → 1,286 items, trial batch, Doppler + `read -s` fallback |

Verification: 620 API tests, 36 extension tests, type-check clean. The documented dry run reproduces 1,266 / 1,286.

## Found

- **Doppler CLI is on the wrong workplace.** It is logged into DoGood (projects: dogood, example-project, secondchance); `upapply` is not visible, so `doppler secrets set UPAPPLY_PASSWORD --project upapply ...` fails. Log into the workplace that owns `upapply`, or use `read -s UPAPPLY_PASSWORD && export UPAPPLY_PASSWORD` in the same shell.
- The local test DB container (`upapply-test-pg`) had stopped; with it down, 208 API tests skip rather than fail. Restarted; the Testing section now warns about this.

## Blocked on you

- Rotate the leaked UpApply password (commit 3b7affc); revoke old OpenAI keys
- Make `UPAPPLY_PASSWORD` available (see above), then say "go" for the ingest loop
- After ingest: review facts, `build-golden`, blind A/B ≥75%, then flip `generation_v2`
- These doc commits need a push + PR to reach main
