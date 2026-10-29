# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

UpApply is an AI-powered Upwork job application system with two components:

1. **API (FastAPI Backend)** - Deployed on Render, handles:
   - User authentication and profile management
   - Memory storage with pgvector semantic search
   - Job analysis and match scoring
   - AI-powered cover letter generation

2. **Chrome Extension** - Sidebar on Upwork pages, provides:
   - Job data extraction from Upwork DOM
   - Real-time job analysis against user profile
   - One-click cover letter generation and insertion
   - Application tracking and analytics

3. **Legacy CLI** (in `src/`) - Original Python CLI tool for reference

## Project Structure

```
UpApply/
├── api/                      # FastAPI backend
│   ├── app/
│   │   ├── api/v1/          # API endpoints
│   │   ├── core/            # Config, database, security, embeddings
│   │   ├── models/          # SQLAlchemy models with pgvector
│   │   ├── schemas/         # Pydantic validation schemas
│   │   └── services/        # Business logic (job analysis, cover letter gen)
│   ├── alembic/             # Database migrations
│   ├── Dockerfile
│   └── pyproject.toml
├── extension/               # Chrome Extension
│   ├── public/             # Manifest and icons
│   └── src/
│       ├── background/     # Service worker
│       ├── content/        # DOM extraction for Upwork
│       ├── lib/            # API client and storage
│       └── sidebar/        # React UI (pages, components)
├── render.yaml             # Render deployment config
└── src/                    # Legacy CLI (reference only)
```

## Secrets Management (Doppler)

Secrets are managed in Doppler project `upapply` with three environments: `dev`, `stg`, `prd`.

```bash
# First-time setup (already configured via doppler.yaml → dev)
doppler setup  # picks up doppler.yaml automatically

# View/edit secrets
doppler secrets --project upapply --config dev
doppler secrets --project upapply --config prd

# Sync prd secrets → Render env vars (then trigger a Render deploy)
./scripts/sync-doppler-to-render.sh
```

Do NOT edit `api/.env` or `extension/.env` directly — those files are kept as fallback only. All canonical values live in Doppler.

## Development Commands

### API Development

```bash
cd api

# Setup (one-time)
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Run migrations (Doppler injects DATABASE_URL)
doppler run --project upapply --config dev -- alembic upgrade head

# Start development server
doppler run --project upapply --config dev -- uvicorn app.main:app --reload --port 8000
```

### Extension Development

```bash
cd extension

# Install dependencies
npm install

# Development with hot reload
doppler run --project upapply --config dev -- npm run dev

# Type checking
npm run type-check

# Production build
doppler run --project upapply --config prd -- npm run build
# Load dist/ folder in chrome://extensions
```

### Testing

```bash
# API - test DB: Postgres 16 + pgvector in Docker on port 55499
# One-time setup only (creates and starts the container):
#   docker run -d --name upapply-test-pg -p 55499:5432 \
#     -e POSTGRES_USER=upapply -e POSTGRES_PASSWORD=upapply -e POSTGRES_DB=upapply_test pgvector/pgvector:pg16
# Every later session:
docker start upapply-test-pg

# API - full suite (tests skip, not fail, when the DB is unreachable — check the skipped count)
(cd api && TEST_DATABASE_URL=postgresql+asyncpg://upapply:upapply@localhost:55499/upapply_test ./venv/bin/pytest -q)

# Extension - unit tests (Vitest) and type check
(cd extension && npx vitest run && npm run type-check)
```

## Database Setup

The API requires PostgreSQL 16+ with pgvector extension:

```sql
CREATE DATABASE upapply;
\c upapply
CREATE EXTENSION vector;
```

For Render deployment, the database is automatically provisioned with pgvector.

## Key Technical Details

### pgvector Semantic Search
Memories and jobs use 1536-dimensional embeddings (OpenAI text-embedding-3-small) with HNSW indexes for fast cosine similarity search:

```python
# Search memories relevant to a job
sql = text("""
    SELECT *, 1 - (embedding <=> :embedding::vector) as similarity
    FROM memories
    WHERE user_id = :user_id
    ORDER BY embedding <=> :embedding::vector
    LIMIT 5
""")
```

### Job Analysis
The job analysis service (`api/app/services/job_analysis.py`) scores jobs against user profiles:
- Skill matching (exact + synonyms)
- Deal breaker detection
- Memory relevance scoring
- Match score calculation (0-100)

### Cover Letter Generation

Two pipelines, selected per user by `user_profiles.generation_v2` (default `false`), checked in `api/v1/jobs.py` and `api/v1/screening_answers.py`.

#### Memory-driven generation (v2, flag on)

Package `api/app/services/generation/`: brief → evidence → write → verify → at most one repair.
- `brief.py` — structured job brief (needs, explicit asks, `domain`) via `extraction_model` (`claude-haiku-4-5`); `domain` is used only for fact search, never shown to the writer
- `evidence.py` — approved **facts** (verified claims, `/api/v1/facts`) ranked per need (0.55·similarity + 0.25·strength + 0.20·win signal), plus up to `DOMAIN_FACTS` closest to the brief's 2-5 word `domain` phrase (so an on-domain product such as FireProofApp reaches the writer; the whole post and the title rank generic SaaS facts higher), plus **voice samples** (past proposals written or edited by the user, never AI-only) for tone
- `writer.py` — `cover_letter_model` (`claude-opus-5-5`, `writer_effort="high"`; no temperature, thinking or prefill), structured output with `fact_ids_used`
- Voice: a user mapped in `api/app/voice/index.json` (email → writer) gets the writer's persona, `sales-proposal` register, house style, soft rules, two exemplar sections and call-offer wording from the vendored ServiceVision voice kit (`api/app/voice/<writer>.json`, loaded by `voice.py`, copied by `scripts/sync_voice_kit.py` from repo `dbbuilder-org/sv-writing-style`, stamped with `kit_version`); users with no mapping get the built-in prompt. To change the voice: update the kit, tag it, re-run the sync script, open a PR
- `verify.py` — rule checks, claim check against evidence, and ≥2 verified specifics (`MIN_SPECIFICS`); failures map to `REPAIR_CODES` for the single repair pass. Users with a voice kit also get the kit's checks (on the letter and the answers, including the answers-only screening path): no em/en dashes or emojis, no de-AI tell-words, `avoid_names` (never "DBBuilder"), a one- or two-sentence opening (`short_opening`), no technology in the close, the close ends on a short call offer (in the kit's exact `call_offer` wording when the request asked for one; refine skips that wording check), and an NDA offer whenever the letter talks about seeing the client's code or documents, written as a clause of the call-offer sentence ("..., and would be willing to sign an NDA in advance"; never "glad to sign an NDA")
- `refine.py` — `POST /api/v1/jobs/cover-letters/{letter_id}/refine` chat with a `search_facts` tool (caps: `MAX_TOOL_ROUNDS=4`, `MAX_TOOL_CALLS=6`, `MAX_FOUND_FACTS=8`)
- Facts: `api/app/services/facts.py` (dedupe at 0.92 cosine; matches of an approved fact auto-approve unless figures conflict or the source is the client) and `fact_extraction.py`; outcome sync credits facts once via `proposals.facts_credited_at`
- **Untrusted text** (job posts, client messages, scraped pages) must pass through `app/services/untrusted.neutralise()` before it reaches any prompt

Design: `docs/superpowers/specs/2026-10-12-memory-driven-generation-design.md`. Plan: `docs/superpowers/plans/2026-10-12-memory-driven-generation.md`. Rollout (ingest, golden set, blind A/B ≥75% before flipping the flag): `docs/superpowers/runbook-memory-driven-generation.md`, using `scripts/ingest_chatgpt_facts.py` and `scripts/eval_generation.py`.

#### Legacy pipeline (flag off)

The legacy pipeline in `api/app/services/cover_letter.py` is corpus-trained and user-specific. See `docs/corpus-guided-cover-letters.md` for full architecture detail.

**Pipeline:**
1. `build_system_prompt(profile, include_call_offer)` — user identity, voice rules, job priority hierarchy, banned phrases, per-user credential requirements from `profile.proposal_anchors["always_include"]`
2. `build_user_prompt(...)` — job context, top-N relevant memories (pgvector), past proposals for voice calibration, per-user job-type credential routing from `profile.proposal_anchors[job_type]`, optional call offer
3. Claude claude-sonnet-4-6 generation (model: `legacy_cover_letter_model` setting)
4. `clean_cover_letter()` — strips salutations, generic sign-offs (preserves "Warm regards,"), placeholders
5. `append_prototype_url()` — appends demo URL sentence if provided
6. `append_closing()` — drops trailing model sign-offs, then appends user's `preferred_closing` once

**Key prompt rules (hard failures if violated):**
- The first word of the letter must not be "I" (nor I'm, I've, I'd, I'll); later sentences may start with "I". Same for the first word of each screening answer (v2)
- No salutation opening (Hello/Hi/Dear/Subject)
- Ends with the user's preferred closing exactly once (`append_closing()` drops model-written sign-offs first)
- Never opens with a quote from the posting; no one-line paragraph ending in a comma or colon; call offer worded "I would be happy to jump on a quick call at no cost or obligation ..." (never "Happy to ...")
- 23 banned phrases that signal generic AI writing
- Length: 300–450 words

**Job priority hierarchy (CTO/Advisory → SaaS/MVP → Full-Stack → SQL/Data → AI/Cloud):**
Each job type maps to a credential anchor in `profile.proposal_anchors`:
- `cto` — founding-to-exit narrative, MBA lead
- `saas` — SchoolVision 20yr/3,000-client SaaS story
- `sql` — 160-server migration + distributed SQL estate
- `cloud` — 160-server Azure migration + AnalyzeMyCloud.com
- `ai` — UpApply (pgvector) + StratVault.ai
- `fullstack` — ServiceVision portfolio demos

**No-cost call offer toggle:**
`CoverLetterGenerateRequest.include_call_offer: bool = True` — when `true`, adds one sentence before the close offering a free, no-commitment call. Exposed as a checkbox in the extension UI (default checked).

### Corpus-Guided Memory System

Two types of memories feed cover letter generation:

**Bio/Achievement memories** — curated JSON, seeded via `scripts/import_chatgpt_corpus.py --bio-only`:
- Format: `scripts/chris_bio_memories.json` (14 entries for Chris)
- Importance scores 0.9–1.0 so they always surface in top-N search

**Past proposal memories** — extracted from ChatGPT export, seeded via `scripts/import_chatgpt_corpus.py --proposals-only`:
- Detects cover letter conversations by title + content patterns
- Stores job posting + final letter together in one embedding
- Used at generation time as voice calibration examples (`PAST WINNING PROPOSALS`)

**Proposal anchors** — per-user JSONB on `user_profiles.proposal_anchors`:
- Seeded via `scripts/seed_proposal_anchors.py`
- Chris's config: `scripts/chris_proposal_anchors.json`
- Controls job-type credential routing and `always_include` items
- Generic users without this field: routing section omitted, generic prompt applies

Full seeding procedure: see `docs/corpus-guided-cover-letters.md` § Installing the Corpus.

### Extension DOM Selectors
The content script (`extension/src/content/upwork-selectors.ts`) uses fallback selectors for Upwork's dynamic DOM. These may need updates if Upwork changes their page structure.

## Deployment

### Render (API)
```bash
# Deploy via render.yaml
render deploy
```

The `render.yaml` configures:
- Web service with Docker
- PostgreSQL 16 with pgvector
- Auto-migration on deploy via `start.sh`

### Chrome Extension
1. Run `npm run build` in `extension/`
2. Go to `chrome://extensions`
3. Enable Developer Mode
4. Click "Load unpacked" and select `extension/dist/`

## Corpus & Memory Scripts

Located in `scripts/`:

| Script | Purpose |
|--------|---------|
| `import_chatgpt_corpus.py` | Extract past proposals + bio memories from ChatGPT export and bulk-import to UpApply API |
| `seed_proposal_anchors.py` | SET `proposal_anchors` JSONB on a user's profile via API PUT |
| `chris_bio_memories.json` | Chris Therriault's 14 canonical bio/achievement memories |
| `chris_proposal_anchors.json` | Chris's job-type credential routing config (cto/saas/sql/cloud/ai/fullstack + always_include) |
| `ingest_chatgpt_facts.py` | v2: send ChatGPT export conversations to `/facts/ingest` as fact candidates. Default `--source signed`: only the final message signed "Chris" / "Chris Therriault" in each conversation, sent as `chatgpt_signed_letter` (the first user message, usually the job post, travels as context only). `--source work`: the user's own turns from work conversations (cover letter in the title or any message, plus career titles); `--source all` (alias `--all`): every conversation. `--dry-run` makes no API calls, `--limit N` caps conversations |
| `eval_generation.py` | v2 rollout gate: `build-golden` (golden jobs from scraped proposals, read-only), `generate` (blind A/B packet, legacy vs v2), `score` (pass ≥75%). `generate` also reports phrases repeated across a batch's openings or closes (`batch_sameness`) |

**Usage (avoid shell `!` in passwords — use Python sys.argv injection):**
```python
python3 -c "
import sys
sys.argv = ['script.py', '--email', 'you@example.com', '--password', 'your!pass', ...]
exec(open('scripts/import_chatgpt_corpus.py').read())
"
```

## Database Migrations

| Version | Description |
|---------|-------------|
| 001 | Initial schema (users, profiles, memories, jobs, applications) |
| 002 | Add cover letter columns |
| 003 | Add preferred_closing to user_profiles |
| 004 | Add screening_answers and proposals tables |
| 005 | Add attachment text fields to jobs |
| 006 | Add beta_feedback table |
| 007 | Lowercase emails |
| 008 | Add job source fields |
| 009 | Add search_queries table |
| 010 | Add job_reviews table |
| 011 | Add work_logs table |
| 012 | Add proposal_anchors JSONB to user_profiles |
| 013 | Add submission tracking fields to cover_letters |
| 014 | Add profile optimization cache columns to user_profiles |
| 015 | Add preferred_client_locations to user_profiles |
| 016 | Add job_queue and user_autonomy_profiles tables |
| 017 | Add outcome_events table |
| 018 | Add draft_cover_letter and draft_status columns to job_queue |
| 019 | Add submission tracking columns to job_queue |
| 020 | Add user_guardrail_configs table |
| 021 | Add global_signal_pool table |
| 022 | Knowledge layer: facts table, voice-sample columns on proposals, memory retrieval flag |
| 023 | Generation v2: cover letter traceability columns + per-user generation_v2 flag |
| 024 | Refine-thread and submitted-final columns on cover_letters, proposals.facts_credited_at |
| 025 | Data: relabel Chris's 14 curated bio memories chatgpt_corpus → bio_import |
| 026 | Add facts.doubtful review flag (marks a candidate doubtful without rejecting it) |

## Environment Variables

### API (.env)
```
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/upapply
OPENAI_API_KEY=sk-...
SECRET_KEY=your-secret-key
CORS_ORIGINS=["chrome-extension://*", "https://www.upwork.com"]
DEFAULT_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
```

### Extension (.env)
```
VITE_API_URL=https://upapply-api.onrender.com
```

## API Endpoints

### Auth
- `POST /api/v1/auth/register` - Create account
- `POST /api/v1/auth/login` - Get JWT token
- `GET /api/v1/auth/me` - Current user info

### Profile
- `GET/PUT /api/v1/profile` - Full profile
- `PUT /api/v1/profile/goals` - Goals section
- `PUT /api/v1/profile/preferences` - Project preferences
- `PUT /api/v1/profile/dealbreakers` - Avoid keywords, minimums
- `PUT /api/v1/profile/pricing` - Rates and availability
- `POST /api/v1/profile/import-resume` - Parse resume with AI

### Memories
- `POST /api/v1/memories` - Create with embedding
- `GET /api/v1/memories` - List all
- `POST /api/v1/memories/search` - Semantic search
- `POST /api/v1/memories/bulk-import` - Bulk import (corpus seeding)

### Jobs
- `POST /api/v1/jobs/analyze` - Analyze without saving
- `POST /api/v1/jobs` - Save and analyze
- `GET /api/v1/jobs/{id}/match` - Detailed match breakdown
- `POST /api/v1/jobs/cover-letters/generate` - Generate cover letter

### Applications
- `POST /api/v1/applications` - Track application
- `PUT /api/v1/applications/{id}/outcome` - Record result
- `GET /api/v1/applications/stats` - Success metrics

### Feedback
- `POST /api/v1/feedback` - Submit feedback
- `GET /api/v1/feedback/analytics/dashboard` - Analytics with insights
