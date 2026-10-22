# Overnight summary — 2026-10-22

Branch `feat/mdg-3-loop` (local only, nothing pushed). Contract: `docs/NEXT.md`, now `status: done`.

## Done

| Step | Commit | Result |
|------|--------|--------|
| 1. CLAUDE.md ingest row | e7906d3 | Default `--source signed` (final Chris-signed letter per conversation); `work` / `all` modes; `--help` confirms |
| 2. Runbook | 5085137 | Signed-letter ingest, Nuxt 3 `__NUXT_DATA__` proposal scrape (pacing, backoff, chunks), `from-proposals` / `from-contracts`, temporary `ipAllowList` commands for build-golden / generate |
| 3. Proposal status | 845cc51 | `pickProposalStatus`: list text (responded / interviewed) beats Upwork's numeric code; archived rows say `archived`; numeric code only as a last resort |

Verification: 644 API tests; extension vitest 60/60 (4 new) and type-check clean.

## To make step 3 count

It changes the extension only. To reach production data: push + PR + merge, rebuild the extension (it bumps to 1.0.19), reload it, and re-run **Sync → Import → Proposals**. Complete proposals are skipped for detail pages but their list rows are still sent, so every stored proposal's status updates to the readable value and outcomes start deriving.

## Blocked on you

- Judge the blind A/B (https://claude.ai/artifact/D6rGtxxbmnGPBDkihzFzQ9), then "score the A/B"; ≥75% → flip `generation_v2`
- Rotate the UpApply password; revoke the dead Render key in git history
- Decisions in `docs/NEXT.md`: Upwork status-code mapping, client-feedback capture, Doppler→Render source of truth, unused-candidate cleanup
- The local doc and extension commits need a push + PR to reach main

The claude.ai account switched back to chris@servicevision.net on 2026-10-22 and the live connections to the A/B and shortlist pages dropped; if either link no longer opens, they can be republished under this account (saved decisions are in each page's database).
