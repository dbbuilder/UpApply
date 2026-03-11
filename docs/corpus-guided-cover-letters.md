# Corpus-Guided Cover Letter Generation in UpApply

**Audience:** Technical PM / senior engineer
**Last updated:** 2026-03-10

---

## Overview

UpApply's cover letter generator is not a generic GPT prompt. It is grounded in three layers of user-specific knowledge:

1. **Bio memories** — curated facts about the user's career, projects, and achievements
2. **Past proposal memories** — every cover letter the user has previously written, extracted from their ChatGPT export
3. **Proposal anchors** — per-user job-type routing rules that tell Claude which credential to lead with for which kind of job

Layers 1 and 2 live in a PostgreSQL + pgvector database and are retrieved semantically at generation time. Layer 3 is a JSONB field on the user's profile, loaded directly at generation time.

This document explains how to build, install, and maintain that knowledge base, and how it flows into generation.

---

## Architecture Overview

```
ChatGPT Export                Bio Memories JSON
(conversations-*.json)        (my_bio_memories.json)
         │                             │
         ▼                             ▼
  import_chatgpt_corpus.py  ──────────────────────►  UpApply API
  (extract + classify)                                /api/v1/memories/bulk-import
         │
         ▼                                            PostgreSQL + pgvector
  Memories table                                      (text-embedding-3-small,
  (title, content, skills,                             1536 dims, HNSW index)
   industry, category,
   importance_score)

  Proposal Anchors JSON                               User profile table
  (chris_proposal_anchors.json)  ──────────────────►  proposal_anchors JSONB field
  seed_proposal_anchors.py

                    At generation time:
                    ┌──────────────────────────────────────────────────────────┐
                    │  Job posting arrives                                      │
                    │      │                                                    │
                    │      ├─► Embed job → pgvector similarity search          │
                    │      │   → top-N relevant memories returned              │
                    │      │                                                    │
                    │      ├─► Load profile.proposal_anchors                   │
                    │      │   → detect job type from title/description        │
                    │      │   → inject matching credential guidance           │
                    │      │                                                    │
                    │      └─► Build prompt → Claude claude-sonnet-4-6 → cover letter │
                    └──────────────────────────────────────────────────────────┘
```

---

## Part 1: The ChatGPT Export

### What it is

When you export your ChatGPT history at https://chatgpt.com → Settings → Data Controls → Export, you receive a zip file containing one or more `conversations-*.json` files. Each file is a JSON array. Each element is a conversation object with:

- `title` — the auto-generated conversation title
- `create_time` — Unix timestamp
- `mapping` — a dict of node objects forming a tree, where each node has `message.author.role` (`user` or `assistant`) and `message.content.parts` (array of text strings)

A corpus of 4,596 conversations across 46 JSON files is the source data for Chris Therriault's UpApply memory set.

### What we extract

The importer (`scripts/import_chatgpt_corpus.py`) identifies **cover letter conversations** by checking whether:
- The conversation title matches patterns like "cover letter", "proposal", "upwork", "job posting", "apply"
- OR the first user message matches content patterns like "write a cover letter", "we are looking for", "hourly rate", "fixed price project"

For each match:
- **Job posting** = the first user message (typically a pasted Upwork job description)
- **Final letter** = the last assistant message (the most refined version after any back-and-forth revisions)

The script walks the conversation tree in DFS order and takes the last assistant turn as the canonical output. If the last assistant message is under 100 characters (an error or clarification), it falls back to the second-to-last.

From a corpus of 4,596 conversations, roughly 800–900 will be cover letter conversations.

---

## Part 2: Memory Structure

Every piece of knowledge is stored as a `Memory` record with this schema:

| Field | Type | Purpose |
|---|---|---|
| `title` | string | Short label used in search results and prompts |
| `content` | text | The full memory text; past proposals include both the job posting and the letter written |
| `category` | enum | `achievement`, `project`, `skill_demo`, `lesson`, `feedback` |
| `skills_demonstrated` | string[] | Tech keywords extracted via keyword scan (e.g., "Azure SQL", "pgvector") |
| `industry` | string | Detected from content (e.g., "Education", "Finance", "SaaS") |
| `project_type` | string | Freeform label (e.g., "Cloud Migration", "Upwork Proposal") |
| `importance_score` | float 0–1 | Higher = retrieved more often; bio/achievement entries are 0.9–1.0 |
| `source` | string | `chatgpt_corpus` or `bio_import` |
| `embedding` | vector(1536) | OpenAI text-embedding-3-small, indexed with pgvector HNSW |

The API endpoint that receives them is `POST /api/v1/memories/bulk-import`, which accepts a `{"memories": [...]}` array, embeds each record server-side, and upserts into the database.

---

## Part 3: Two Types of Memories

### Type A — Bio/Achievement Memories

These are curated, hand-written facts about the user. They are not extracted from the corpus automatically — they represent the canonical version of the user's identity.

**File:** `scripts/chris_bio_memories.json`
**Format:** JSON array of memory objects (see schema above)

Chris's 9 entries cover:
- The 160-server datacenter-to-Azure migration
- DBBuilder, Inc. — 25+ years enterprise software
- SchoolVision — 20+ year K-12 SaaS, 3,000 clients
- UpApply — AI/pgvector/GPT-4o proposal automation
- ServiceVision.net — consulting brand + live demo portfolio
- Multi-tenant SaaS architecture pattern
- SQL Server expertise (stored procs, CTEs, indexing, replication)
- Azure architect skills (all major services)
- Upwork proposal style and tone preferences

Importance scores are 0.9–1.0, so they surface at the top of every relevant similarity search.

**To create a bio file for a new user:**

```json
[
  {
    "title": "Signature achievement title",
    "content": "Full narrative description of the achievement...",
    "category": "achievement",
    "skills_demonstrated": ["Python", "Azure", "React"],
    "industry": "Healthcare",
    "project_type": "HIPAA Compliance Platform",
    "outcome": "Quantified outcome if available",
    "importance_score": 1.0
  }
]
```

### Type B — Past Proposal Memories

Each past proposal memory encodes:

```
JOB POSTING:
<first 1,500 chars of the job description>

PROPOSAL WRITTEN:
<first 2,000 chars of the final cover letter>
```

Both halves are embedded together so the record is retrievable by either job description similarity or writing style similarity. Skills and industry are auto-detected via keyword scan across 70+ tech terms and 20+ industry categories.

At generation time, the top-5 most semantically similar past proposals are passed to Claude as **voice calibration examples** — not as content to copy, but as style anchors.

---

## Part 4: Installing the Corpus

### Prerequisites

- Python 3.x with `requests` installed (system Python works; not the UpApply venv)
- UpApply account credentials
- ChatGPT export directory (containing `conversations-*.json` files)
- Bio memories JSON file

### Step 1 — Dry run (no data written)

```bash
python3 scripts/import_chatgpt_corpus.py \
  --data-dir /path/to/chatgpt-export \
  --bio-file scripts/chris_bio_memories.json \
  --email you@example.com \
  --password yourpassword \
  --dry-run
```

This prints how many conversations were found, what categories were detected, and previews the first 3 memories of each type. Nothing is written.

### Step 2 — Import bio memories first

```bash
python3 -c "
import sys
sys.argv = [
  'import_chatgpt_corpus.py',
  '--data-dir', '/path/to/chatgpt-export',
  '--bio-file', 'scripts/chris_bio_memories.json',
  '--email', 'you@example.com',
  '--password', 'yourpassword',
  '--bio-only',
]
exec(open('scripts/import_chatgpt_corpus.py').read())
"
```

> **Note on passwords with special characters:** If your password contains `!` or other shell-special characters, use the Python `sys.argv` injection pattern above rather than passing via shell arguments. This avoids zsh history expansion.

### Step 3 — Import past proposals

```bash
python3 -c "
import sys
sys.argv = [
  'import_chatgpt_corpus.py',
  '--data-dir', '/path/to/chatgpt-export',
  '--bio-file', 'scripts/chris_bio_memories.json',
  '--email', 'you@example.com',
  '--password', 'yourpassword',
  '--proposals-only',
  '--batch-size', '10',
]
exec(open('scripts/import_chatgpt_corpus.py').read())
"
```

Batches of 10 memories are sent with a 0.75s delay between batches. The API embeds each batch server-side using OpenAI text-embedding-3-small.

### Step 4 — Install proposal anchors

The proposal anchors live in the user's profile and control job-type-specific credential routing at generation time.

1. Create your anchors JSON (or copy `scripts/chris_proposal_anchors.json` as a template):

```json
{
  "always_include": [
    "Your credential — weave into narrative, never just list it",
    "Your signature achievement — anchor every relevant claim"
  ],
  "cto": "For CTO/leadership jobs — what to lead with...",
  "saas": "For SaaS/MVP jobs — what to reference...",
  "sql": "For SQL/data jobs — what to anchor on...",
  "cloud": "For cloud/Azure/AWS jobs — what to anchor on...",
  "ai": "For AI/ML/RAG jobs — what to reference...",
  "fullstack": "For full-stack jobs — what to reference..."
}
```

2. Seed into the API:

```bash
python3 -c "
import sys
sys.argv = [
  'seed_proposal_anchors.py',
  '--api-url', 'https://upapply-api.onrender.com',
  '--email', 'you@example.com',
  '--password', 'yourpassword',
  '--anchors-file', 'scripts/my_proposal_anchors.json',
]
exec(open('scripts/seed_proposal_anchors.py').read())
"
```

The script GETs the existing profile, merges in the anchors, and PUTs the full profile back. Existing profile fields are not touched.

---

## Part 5: How the Corpus Guides Generation

When a user generates a cover letter, the system executes this sequence in `cover_letter.py`:

### 1. System Prompt — User Identity Layer

`build_system_prompt(profile)` builds the static framing Claude receives before any job context. It includes:

- The user's name, professional title, bio (first 400 chars), career goals, communication style, and unique strengths — all from the `UserProfile` record
- Universal voice rules: peer-to-peer tone, pattern recognition hook, one concrete story, failure modes, no bullets
- Universal sentence rules: no sentence starts with "I", no salutation, ends with "Warm regards,"
- Universal job priority hierarchy: CTO/Advisory → SaaS/MVP → Full-Stack → SQL/Data → AI/Cloud
- Universal banned phrases list (23 phrases that signal generic AI writing)
- **Per-user always_include block** — pulled from `profile.proposal_anchors["always_include"]` if set; injected as a "PER-USER CREDENTIAL REQUIREMENTS" section

For users without `proposal_anchors`, this section is omitted and the prompt remains fully generic.

### 2. User Prompt — Job Context + Memory Retrieval

`build_user_prompt(...)` assembles the job-specific prompt:

1. **Job title + description** (first 2,500 chars)
2. **Required skills and budget** from the job posting
3. **Relevant memories** — the top-N memories returned by pgvector similarity search against the job embedding, formatted as a numbered list with title, content snippet, and outcome. Claude is told to draw from these for the "concrete story" section of the letter.
4. **Skill alignment notes** — which required skills the user has (exact or related matches), as background context only; never listed explicitly
5. **Past winning proposals** — the top past proposals by semantic similarity, passed as style calibration examples. Proposals marked `was_hired = True` are labeled `[SUCCESSFUL - Got Hired]` and weighted more heavily.
6. **Per-user job-type credential guidance** — pulled from `profile.proposal_anchors[job_type]` where `job_type` is detected by scanning the job title + first 500 chars of description for keyword signals (e.g., "sql server" → `sql`, "llm" → `ai`, "cto" → `cto`). If the user has no anchors, this section is skipped.
7. **Final instruction** — instructs Claude to start with the pattern recognition hook, use the most relevant portfolio story specifically, name failure modes, anchor with portfolio products, and remember the "I" and "Warm regards," rules.

### 3. Post-Processing

After Claude returns the generated text, `clean_cover_letter()` applies deterministic cleanup:

- Strips `Subject:` lines
- Strips salutation lines (`Dear...`, `Hello`)
- Strips generic sign-offs (`Sincerely,`, `Regards,`, `Best,`) — but explicitly preserves `Warm regards,`
- Removes bracketed placeholders like `[Your Name]`
- Removes trailing generic signatures via regex
- Collapses extra whitespace

Then `append_prototype_url()` appends the demo prototype sentence if a URL was provided for the job, and `append_closing()` adds the user's configured closing signature.

---

## Part 6: What "Corpus-Guided" Actually Means

Without the corpus, Claude generates a plausible-sounding cover letter that could have been written for anyone. With it:

| Without corpus | With corpus |
|---|---|
| Generic "I have experience in X" | Names specific projects: "SchoolVision ran this pattern across 3,000 client databases" |
| Generic voice calibration | Voice matched to 800+ past letters from this specific user |
| No credential routing | Knows to lead with the 160-server migration for Azure jobs, UpApply/StratVault for AI jobs |
| May omit MBA | Always includes MBA because `always_include` mandates it |
| May start sentences with "I" | Hard rule prevents it at both prompt and post-processing layers |

The memories retrieved by pgvector don't just provide facts — they provide the **specific language patterns, project names, and outcome statements** that Claude weaves into the narrative. Past proposals provide **voice fingerprinting**: the pacing, sentence structure, and level of technical detail that characterize this user's writing.

---

## Part 7: Maintaining the Corpus

### Re-seeding after a new ChatGPT export

Run the import script again with `--proposals-only`. The bulk-import endpoint is idempotent by title hash — duplicate titles are skipped.

### Updating bio memories

Edit `scripts/chris_bio_memories.json` (or your equivalent) and re-run with `--bio-only`. Existing memories with the same title will be overwritten.

### Updating proposal anchors

Edit `scripts/chris_proposal_anchors.json` (or your equivalent) and re-run `seed_proposal_anchors.py`. The script always does a full GET + PUT, so all anchor keys are replaced atomically.

### Verifying retrieval

```bash
curl -s https://upapply-api.onrender.com/api/v1/memories/search \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "Azure SQL Server migration", "limit": 5}' | python3 -m json.tool
```

The top results should include the 160-server migration and SchoolVision memories for an Azure query.

---

## File Reference

| File | Purpose |
|---|---|
| `scripts/import_chatgpt_corpus.py` | Main corpus importer — generic, works for any user |
| `scripts/chris_bio_memories.json` | Chris Therriault's 9 canonical bio/achievement memories |
| `scripts/chris_proposal_anchors.json` | Chris's job-type credential routing config |
| `scripts/seed_proposal_anchors.py` | Seeds proposal_anchors into any user's profile via API |
| `api/app/services/cover_letter.py` | Generation pipeline: system prompt, user prompt, post-processing |
| `api/app/models/user.py` | `UserProfile.proposal_anchors` JSONB field definition |
| `api/alembic/versions/012_add_proposal_anchors.py` | DB migration adding the proposal_anchors column |

---

## Design Decisions

**Why store past proposals as memories rather than a separate table?**
The pgvector similarity search that retrieves relevant project memories also retrieves style-matched past proposals in a single query pass. Storing them in the same table means one embedding lookup serves both purposes.

**Why is job-type routing in the profile (not the prompt template)?**
Every user's anchor stories are different. Hardcoding them in the prompt template would mean every new user gets Chris's credentials. Moving them to the profile means the same code path serves any user — the credential injection is simply absent if `proposal_anchors` is null.

**Why use the last assistant message as the final letter?**
Users almost always revise toward quality. The last assistant message in a multi-turn cover letter conversation is the most refined version after all corrections and additions. Taking the last message captures the "approved" output, not an early draft.

**Why keyword extraction rather than NLP for skill detection?**
The skill vocabulary is small and stable. A keyword scan across 70+ explicitly defined terms is fast, transparent, and correct for the domain. An NLP approach would add model overhead for no meaningful gain over a manually maintained dictionary.
