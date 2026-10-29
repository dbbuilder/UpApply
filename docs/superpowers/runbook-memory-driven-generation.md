# Memory-Driven Generation — Production Runbook

Companion to the [spec](specs/2026-10-12-memory-driven-generation-design.md) and
[plan](plans/2026-10-12-memory-driven-generation.md). Every step is safe to stop after;
nothing changes letter output until step 7 flips the per-user flag.

## 0. Before anything (security)
- Rotate the UpApply account password (it is in pushed commit `3b7affc`; redaction does not remove history).
- Revoke the old OpenAI keys listed in `docs/SESSION_CONTEXT_2026-06-18.md`.

## 1. Merge PRs #8 → #9 → #10 → #11 in order
After each merge, retarget the next PR's base to `main` before merging it.

## 2. Deploy
Render runs `alembic upgrade head` on start (`api/start.sh`), applying 022 → 023 → 024.
Verify: `SELECT version_num FROM alembic_version;` → `024_refine_loop`.

## 3. Relabel the curated bio memories (one-time)
They were seeded tagged `chatgpt_corpus`, which `/facts/from-memories` (correctly) does not
trust. The import script now tags them `bio_import`; existing rows need this one-time fix.
Matched by exact title and owner — nothing else is touched.

**Done automatically by migration `025_relabel_bio_memories` on deploy** (the prod DB is not
reachable from outside Render). The SQL below is the same change, kept for reference:

```sql
BEGIN;
-- Preview: expect 14 rows (13 bio + 1 'lesson', which fact import skips anyway)
SELECT m.title, m.source, m.importance_score, m.category
  FROM memories m JOIN users u ON u.id = m.user_id
 WHERE u.email = 'chris@servicevision.net'
   AND m.source = 'chatgpt_corpus'
   AND m.title IN (
    'Stratavault.ai — Private enterprise AI knowledge base with RAG and PII protection',
    'AestheticIQ.ai — AI business intelligence SaaS for medical spas',
    'AnalyzeMyCloud.com — AI-powered cloud cost optimization service',
    'Remote2Me.com — Enterprise zero-trust remote control platform',
    'FireProofApp.net — Fire extinguisher inspection and compliance SaaS',
    'Migrated 160-server datacenter to Azure hybrid cloud',
    'SaaS company founded 2001 — 25+ years enterprise software',
    'K-12 education SaaS platform — 20+ years operating, 3,000 clients',
    'UpApply — AI-powered Upwork proposal automation',
    'ServiceVision.net — Technology consulting and AI integration',
    'Multi-tenant SaaS architecture: 3,000 per-client SQL Server databases',
    'SQL Server expert: stored procedures, CTEs, indexing, replication',
    'Azure cloud architect: App Service, Functions, Front Door, Key Vault, DevOps',
    'Upwork proposal style and tone preferences'
   );

UPDATE memories m SET source = 'bio_import'
  FROM users u
 WHERE u.id = m.user_id AND u.email = 'chris@servicevision.net'
   AND m.source = 'chatgpt_corpus'
   AND m.title IN (
    'Stratavault.ai — Private enterprise AI knowledge base with RAG and PII protection',
    'AestheticIQ.ai — AI business intelligence SaaS for medical spas',
    'AnalyzeMyCloud.com — AI-powered cloud cost optimization service',
    'Remote2Me.com — Enterprise zero-trust remote control platform',
    'FireProofApp.net — Fire extinguisher inspection and compliance SaaS',
    'Migrated 160-server datacenter to Azure hybrid cloud',
    'SaaS company founded 2001 — 25+ years enterprise software',
    'K-12 education SaaS platform — 20+ years operating, 3,000 clients',
    'UpApply — AI-powered Upwork proposal automation',
    'ServiceVision.net — Technology consulting and AI integration',
    'Multi-tenant SaaS architecture: 3,000 per-client SQL Server databases',
    'SQL Server expert: stored procedures, CTEs, indexing, replication',
    'Azure cloud architect: App Service, Functions, Front Door, Key Vault, DevOps',
    'Upwork proposal style and tone preferences'
   );
-- Expect: UPDATE 14 (or fewer if some were never imported). If not, ROLLBACK.
COMMIT;
```

## 4. Load the knowledge base
1. **Bio facts** (auto-approved, trusted): `POST /api/v1/facts/from-memories` — repeat until `remaining` is 0.
2. **ChatGPT export**: unzip only the conversation files to `working/chatgpt-export/` (gitignored):
   `unzip -oq <export>.zip 'conversations*.json' -d working/chatgpt-export`.
   By default (`--source signed`) the script sends only the **final message signed "Chris" /
   "Chris Therriault"** in each conversation, as `chatgpt_signed_letter`: letters sent under the
   freelancer's name, so their claims are endorsed; the first user message (usually the job post)
   is context only. The 2026-10 export: **315 signed letters of 5,148 conversations**.
   `--source work` sends the user's own turns from work conversations (cover letter in the title
   or any message, plus career titles: 1,266 conversations → 1,286 items); `--source all` (alias
   `--all`) sends everything. Personal, medical, family and how-to chats never leave the machine
   in the default or work modes. Store the password once in
   Doppler (`doppler secrets set UPAPPLY_PASSWORD --project upapply --config dev`; it prompts),
   then trial a batch before the full run (re-runs skip conversations already ingested). The Doppler
   CLI must be logged into the workplace that holds `upapply` (`doppler projects` lists it); without
   Doppler, `read -s UPAPPLY_PASSWORD && export UPAPPLY_PASSWORD` in the same shell works too
   (or omit it and the script prompts):
   ```bash
   api/venv/bin/python scripts/ingest_chatgpt_facts.py working/chatgpt-export --dry-run   # counts, no API calls
   doppler run --project upapply --config dev -- api/venv/bin/python scripts/ingest_chatgpt_facts.py working/chatgpt-export \
       --email chris@servicevision.net --source signed --limit 50        # trial, then drop --limit
   ```
3. **Upwork proposals**: load the extension (≥1.0.18), open Upwork → Proposals, then sidebar
   **Sync → Import → Proposals → Run** and keep the sidebar open. Each detail page is scraped for the
   full letter, screening answers, job text and status.
   - Upwork's proposal pages are **Nuxt 3**: `window.__NUXT__` is `{}` and the data lives in
     `<script id="__NUXT_DATA__">` (an index-referenced payload). The extension decodes it
     (`reviveNuxtPayload` / `proposalFromNuxtData` in `extension/src/lib/proposal-scrape.ts`) from
     `vuex['proposal-details'].proposalDetailsV3Response`; the rendered page is the fallback.
   - Pacing: 6–10 s between pages; on Upwork's "There was an error loading this page" toast it
     backs off 30/60/120 s and stops after 3 throttled proposals in a row (run again later).
   - It saves every 10 proposals, works in ~4-minute chunks the sidebar resumes automatically,
     reads the proposal lists once per run, and skips proposals already stored complete
     (letter ≥300 + job text ≥200 chars) — re-runs are safe and pick up where they stopped.
   - Statuses arrive as Upwork's numeric codes ('7' = active submitted); most outcomes stay
     unknown until those are mapped.
   Then `POST /api/v1/facts/from-proposals` until `remaining` is 0 (10 proposals per call;
   2026-10: 166 proposals → 1,362 candidates).
4. **Contracts** (optional): `POST /api/v1/facts/from-contracts` until `remaining` is 0 (client
   quotes always go to review). The Won Contracts import stores titles and dates, not client
   feedback text, so this yields only weak role/project records today.
5. **Review**: extension → Me → Facts. Approve/edit/reject candidates. Target 80–200 approved.

## 5. Build the golden set (read-only)
Steps 5 and 6 read the production database directly, and Render's Postgres refuses external
connections (empty `ipAllowList`). Open it **temporarily** for this Mac's IP, and clear it again
straight after step 6 (the Render API key is in the Keychain as `cc:render-22eb83`, the external
DB URL as `cc:db-5c2ea0`):
```bash
IP=$(curl -s https://api.ipify.org); R=$(security find-generic-password -s cc:render-22eb83 -w)
curl -X PATCH -H "Authorization: Bearer $R" -H "Content-Type: application/json" \
  -d "{\"ipAllowList\":[{\"cidrBlock\":\"$IP/32\",\"description\":\"temp: UpApply eval\"}]}" \
  https://api.render.com/v1/postgres/dpg-d5hnlqer433s73bskf8g-a
# ... steps 5 and 6 ...
curl -X PATCH -H "Authorization: Bearer $R" -H "Content-Type: application/json" \
  -d '{"ipAllowList":[]}' https://api.render.com/v1/postgres/dpg-d5hnlqer433s73bskf8g-a
```
```bash
cd api && doppler run --project upapply --config prd -- env DATABASE_URL="$(security find-generic-password -s cc:db-5c2ea0 -w)" \
  ./venv/bin/python ../scripts/eval_generation.py build-golden --email chris@servicevision.net --out ../docs/evals/golden.json
```
Needs ≥15 eligible jobs (letters you wrote/edited with the job post captured); it warns otherwise —
scrape more proposal details first.

## 6. Blind A/B (commits nothing; ≈$0.10/job)
```bash
cd api && doppler run --project upapply --config prd -- env DATABASE_URL="$(security find-generic-password -s cc:db-5c2ea0 -w)" \
  ./venv/bin/python ../scripts/eval_generation.py generate \
  --email chris@servicevision.net --golden ../docs/evals/golden.json
```
Fill `docs/evals/<date>/scores.csv` (A, B or tie) **without opening `key.json`**, then
`./venv/bin/python ../scripts/eval_generation.py score --run-dir ../docs/evals/<date>`.
Pass = new preferred in ≥75% of pairs, zero unsupported claims.

### Rounds 3-4: running another round
- **Voice first.** Chris's notes go into the voice kit (`~/dev2/sv/writing-style`, repo
  `dbbuilder-org/sv-writing-style`): log them verbatim in `chris/feedback-log.md`, change
  `chris/rules.yaml` / the register, run `python3 tools/build.py chris` and the kit tests, merge and
  tag. Then vendor it here with `api/venv/bin/python scripts/sync_voice_kit.py` (stamps `kit_version`
  into `api/app/voice/chris.json`) and open a PR.
- **New seed every round** (`--seed`, e.g. the date) so A/B sides are reshuffled, and a new
  `--out-dir` (`docs/evals/<date>-r<n>`).
- **Resume.** `generate` saves each finished job as `<out-dir>/partial/<job_id>.json` and skips
  saved jobs on the next run, and retries a job once on a dropped DB connection. After a dropped
  connection or an AI proxy 504, rerun the same command; delete `partial/` only when the code
  changed and every job must be regenerated.
- **Read the generate output before publishing.** It prints the `sameness` report (four-word
  phrases repeated across 15%+ of a batch's openings or closes, for both sides); the same report and
  each draft's evidence statements (`new_meta.<job_id>.evidence`) are saved in `key.json`. Use them
  only for diagnosis, after scoring, never to inform the judging.
- **Judging page.** Seed the blind page's `review/pairs` doc from `pairs.md` / `key.json` sides
  (title, job post, the letter actually sent, A, B). claude.ai pages belong to the account that
  published them and became unreachable when the session switched accounts (rounds 3-4). If the
  page cannot be read back, Chris fills `scores.csv` from `pairs.md` directly; scoring needs only
  that file and `key.json`.

## 7. Flip the flag (only after a pass)
```sql
UPDATE user_profiles SET generation_v2 = true
 WHERE user_id = (SELECT id FROM users WHERE email = 'chris@servicevision.net');
```
**Rollback** at any time: same statement with `false` — the legacy path is untouched.

## 8. After 2 weeks on v2
Remove the legacy generation path and corpus-memory retrieval code (spec §4.3 step 6).

## 9. Measuring and feedback

All three tools below read or write the production database, so open the Render Postgres
`ipAllowList` for this Mac first and clear it straight after (§5).

### Results report (read-only)
```bash
(cd api && doppler run --project upapply --config prd -- env DATABASE_URL="$(security find-generic-password -s cc:db-5c2ea0 -w)" \
  ./venv/bin/python ../scripts/outcome_report.py --email chris@servicevision.net)
```
Optional flags: `--since 2026-10-28` (start of the v2 group) and `--json` (machine-readable output).
- **Groups:** `v2` = proposals whose sent letter (`outcomes.find_sent_letter`, the same link outcome
  sync uses) was written by the v2 engine, sent on or after `--since` (default: the user's first v2
  cover letter); `baseline` = every other proposal sent in the 90 days before. Each group is also
  split by the job's match-score band.
- **Rates** (viewed, replied, interview, hired) are over decided proposals only. Proposals still at
  submitted/viewed and younger than 14 days are **pending**; proposals whose stage is **unknown** are
  listed separately. Neither counts in a denominator. A rate over fewer than 5 proposals prints `n<5`.
- Median days to first reply comes from the `proposal_stage_events` ledger (real stage changes only).

### Proposal stages
`app/services/proposal_status.py` maps raw statuses (Upwork numeric codes, list text, sidebar and
outcome-sync values) to one stage: submitted, viewed, replied, interview, hired, declined, closed or
unknown. `proposals.stage` follows `status` automatically and every change is appended to
`proposal_stage_events`; re-imports only move a proposal forward.
- Only map an Upwork numeric code once its meaning is confirmed (today only `7` = submitted). Add it
  to `STAGE_ALIASES`; new keys are allowed, but changing what an existing key maps to fails
  `tests/test_migration_027.py`, because migration 027 backfilled with that map.
- Re-running the extension's Proposals import (Sync → Import → Proposals) is what turns the
  `unknown` stages into readable ones.

### Client feedback from the Upwork profile
Copy one page of the profile's work history (title, rating, dates, the client's quote, "Endorsed by
client" chips) into a text file, then:
```bash
api/venv/bin/python scripts/import_upwork_feedback.py page1.txt --dry-run      # see the candidates
doppler run --project upapply --config prd -- env DATABASE_URL="$(security find-generic-password -s cc:db-5c2ea0 -w)" \
  api/venv/bin/python scripts/import_upwork_feedback.py page1.txt --email chris@servicevision.net
```
Each quote becomes a `client_quote` candidate (source `client_feedback`), which always waits for
approval in the extension (Me → Facts). Amounts, rates and hours on the page are dropped; quotes
Upwork shortens ("See more") are marked; `--include-endorsements` adds jobs that have chips but no
quote. Re-running a page is safe: the facts service merges near-duplicates.

### New-user checklist (before turning `generation_v2` on)
1. The user registers through the extension.
2. Load facts: their Upwork proposals (extension import, then `POST /api/v1/facts/from-proposals`,
   repeated until `remaining` is 0: each call processes 10 proposals),
   their ChatGPT export (§4) and client feedback (above); they approve candidates in Me → Facts.
3. Check `GET /api/v1/profile/setup-status`: `ready` needs at least 25 approved facts, at least one
   voice sample (a non-empty proposal they wrote or edited, with a job embedding; run
   `POST /api/v1/proposals/backfill-job-embeddings` for proposals saved before embeddings existed)
   and their name and professional title. `missing` lists what is left. An UpApply draft sent
   unchanged (under 5% of words edited) counts as AI, not as a voice sample.
4. Optional: a voice kit for them in `~/dev2/sv/writing-style` (built from their own A/B feedback).
5. Turn the flag on for that user only (§7, with their email).
