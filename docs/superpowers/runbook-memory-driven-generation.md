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
   By default the script sends **work conversations only**: any whose title or messages mention a
   cover letter, plus career-titled ones (proposal, CV, bio, interview, RFP, role...). Personal,
   medical, family and how-to chats never leave the machine; `--all` disables the filter. The
   2026-10 export: **1,266 of 5,148 conversations → 1,286 items**. Store the password once in
   Doppler (`doppler secrets set UPAPPLY_PASSWORD --project upapply --config dev`; it prompts),
   then trial a batch before the full run (re-runs skip conversations already ingested). The Doppler
   CLI must be logged into the workplace that holds `upapply` (`doppler projects` lists it); without
   Doppler, `read -s UPAPPLY_PASSWORD && export UPAPPLY_PASSWORD` in the same shell works too
   (or omit it and the script prompts):
   ```bash
   api/venv/bin/python scripts/ingest_chatgpt_facts.py --dry-run          # counts, no API calls
   doppler run --project upapply --config dev -- api/venv/bin/python scripts/ingest_chatgpt_facts.py \
       --email chris@servicevision.net --limit 50                         # trial, then drop --limit
   ```
3. **Upwork proposals**: load the extension, open Upwork → Proposals (active + archived) and run the
   proposal import so each detail page is scraped (full letter, answers, job text, status).
   Then `POST /api/v1/facts/from-proposals` until `remaining` is 0.
4. **Contracts** (optional): `POST /api/v1/facts/from-contracts` (client quotes always go to review).
5. **Review**: extension → Me → Facts. Approve/edit/reject candidates. Target 80–200 approved.

## 5. Build the golden set (read-only)
```bash
cd api && doppler run --project upapply --config prd -- \
  ./venv/bin/python ../scripts/eval_generation.py build-golden --email chris@servicevision.net
```
Needs ≥15 eligible jobs (letters you wrote/edited with the job post captured); it warns otherwise —
scrape more proposal details first.

## 6. Blind A/B (commits nothing; ≈$0.10/job)
```bash
cd api && doppler run --project upapply --config prd -- \
  ./venv/bin/python ../scripts/eval_generation.py generate \
  --email chris@servicevision.net --golden ../docs/evals/golden.json
```
Fill `docs/evals/<date>/scores.csv` (A, B or tie) **without opening `key.json`**, then
`./venv/bin/python ../scripts/eval_generation.py score --run-dir ../docs/evals/<date>`.
Pass = new preferred in ≥75% of pairs, zero unsupported claims.

## 7. Flip the flag (only after a pass)
```sql
UPDATE user_profiles SET generation_v2 = true
 WHERE user_id = (SELECT id FROM users WHERE email = 'chris@servicevision.net');
```
**Rollback** at any time: same statement with `false` — the legacy path is untouched.

## 8. After 2 weeks on v2
Remove the legacy generation path and corpus-memory retrieval code (spec §4.3 step 6).
