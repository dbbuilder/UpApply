# Session Context — 2026-03-11

**Project:** UpApply
**Path:** `/Users/admin/dev2/UpApply`
**Repository:** https://github.com/dbbuilder/UpApply

---

## What Was Done This Session

This session built the corpus-guided cover letter system and wired it end-to-end into UpApply. Three major workstreams:

---

## 1. ChatGPT Corpus Analysis & Memory Extraction

**Source data:** 4,596 ChatGPT conversations across 46 JSON files in `/Users/admin/dev2/OpenAIData/`

**Outputs:**
- `/Users/admin/dev2/OpenAIData/memory_extraction.txt` — all titles + tech frequency counts
- `/Users/admin/dev2/OpenAIData/chris_memory_analysis.md` — 34KB full professional profile
- `/Users/admin/dev2/OpenAIData/cover_letter_patterns.md` — 48KB cover letter pattern analysis from 818 conversations

**Key findings from corpus analysis:**
- 57.3% of revision requests = "Add specific detail/experience" (model was too generic)
- MBA omitted by the model in 10+ explicit conversations
- Optimal length: 300–400 words (not 200–300 as previously configured)
- Never open with "I am writing to apply" (101 instances, always revised away)
- Never begin a sentence with "I" — consistent pattern across hundreds of corrections
- Always close with "Warm regards," — user's consistent preference
- No-cost call offer: common closing element in successful proposals
- Top job category: SQL/Database (66.7%), AI/ML (11.2%)

---

## 2. Permanent Profile & Identity Files

**`/Users/admin/.config/claude/chris-profile.md`** — Permanent professional identity for Claude, generated from corpus. Added to `/Users/admin/CLAUDE.md` reference table.

Identity rules:
- Chris Therriault = professional identity only
- Ted = personal, completely separate, never included in professional memory
- No lived experience / Empower Reentry / Communities of Belonging references
- Interests: History (broad — American, world, military, Pacific Northwest), cooking, Thomas Kinkade art, creative writing, Disney

---

## 3. UpApply Cover Letter Prompt Overhaul

**File:** `api/app/services/cover_letter.py`

### `clean_cover_letter()` changes
- Strips `Hello` / `Hello,` openings
- Strips generic sign-offs (Sincerely, Regards, Best, Thank you) but preserves "Warm regards,"
- Regex strips trailing generic signatures but not "Warm regards,"

### `build_system_prompt(profile, include_call_offer)` changes
- Added SENTENCE RULES: no sentence starts with "I", no salutation, always ends "Warm regards,"
- Added JOB PRIORITY hierarchy: CTO/Advisory → SaaS/MVP → Full-Stack → SQL/Data → AI/Cloud
- Added ALWAYS INCLUDE (generic) + per-user block from `profile.proposal_anchors["always_include"]`
- Added BANNED PHRASES list (23 phrases that signal generic AI writing)
- STRUCTURE step 5: call offer (conditional on `include_call_offer` flag)
- Length corrected: 300–450 words

### `build_user_prompt(..., include_call_offer)` changes
- Per-user job-type credential routing from `profile.proposal_anchors[job_type]`
  - Detects job type from title + first 500 chars of description
  - Maps keywords → anchor key → guidance text
  - If user has no `proposal_anchors`: section omitted (generic users unaffected)
- Call offer reminder injected into final instruction when enabled

---

## 4. Per-User Proposal Anchors (Migration 012)

**Problem:** Chris's credential routing was hardcoded — would apply to all users.

**Solution:** `proposal_anchors` JSONB field on `UserProfile`.

**Files changed:**
- `api/alembic/versions/012_add_proposal_anchors.py` — migration
- `api/app/models/user.py` — `proposal_anchors: Optional[dict]` field
- `api/app/schemas/profile.py` — added to `ProfileCreate`, `ProfileUpdate`, `ProfileResponse`
- `api/app/services/cover_letter.py` — reads from field, not hardcoded

**Schema (`profile.proposal_anchors`):**
```json
{
  "always_include": ["credential 1", "credential 2"],
  "cto": "guidance text for CTO/leadership jobs",
  "saas": "guidance text for SaaS/MVP jobs",
  "sql": "guidance text for SQL/data jobs",
  "cloud": "guidance text for cloud/infrastructure jobs",
  "ai": "guidance text for AI/ML/RAG jobs",
  "fullstack": "guidance text for full-stack jobs"
}
```

**Scripts:**
- `scripts/chris_proposal_anchors.json` — Chris's anchors (already seeded)
- `scripts/seed_proposal_anchors.py` — generic seeder for any user (GET + merge + PUT)

---

## 5. ChatGPT Corpus Importer

**File:** `scripts/import_chatgpt_corpus.py`

Generic importer for any user. Extracts:
- **Proposal memories** from `conversations-*.json` files — job posting + final letter stored together
- **Bio memories** from user-supplied JSON (`--bio-file`)

**Chris's bio:** `scripts/chris_bio_memories.json` (9 entries, importance 0.9–1.0)

**Usage (use Python sys.argv to avoid shell `!` escaping issues):**
```python
python3 -c "
import sys
sys.argv = ['import_chatgpt_corpus.py',
  '--data-dir', '/Users/admin/dev2/OpenAIData',
  '--bio-file', 'scripts/chris_bio_memories.json',
  '--email', 'chris@servicevision.net', '--password', 'Gv51076!',
  '--dry-run']   # remove --dry-run to import
exec(open('scripts/import_chatgpt_corpus.py').read())
"
```

---

## 6. Include No-Cost Call Offer Toggle

**Files changed:**
- `api/app/schemas/job.py` — `include_call_offer: bool = True` on `CoverLetterGenerateRequest`
- `api/app/api/v1/jobs.py` — passed through to service
- `api/app/services/cover_letter.py` — both `build_system_prompt()` and `build_user_prompt()` respect flag
- `extension/src/lib/api-client.ts` — `include_call_offer?: boolean` in interface
- `extension/src/sidebar/store.ts` — `includeCallOffer` param on `generateCoverLetter()`
- `extension/src/sidebar/pages/Generator.tsx` — checkbox UI (default checked), wired to all generate calls

---

## 7. Documentation Added

- `docs/corpus-guided-cover-letters.md` — Full technical PM-level explainer of the corpus system
- `CLAUDE.md` — Updated cover letter section, added corpus/scripts/migrations sections
- `docs/SESSION_CONTEXT_2026-03-11.md` — This file

---

## Deployment State (end of session)

| Item | Status |
|------|--------|
| API | Live — https://upapply-api.onrender.com |
| Migration 012 (proposal_anchors) | Applied |
| Cover letter prompt | Updated + live |
| proposal_anchors (Chris) | Seeded |
| Corpus bio memories (9) | Seeded |
| Extension | Built — load `extension/dist/` via chrome://extensions |

---

## Gotchas

- **Shell `!` in passwords**: zsh expands `!` even in single quotes. Always use Python `sys.argv` injection for scripts that accept passwords.
- **UpApply venv vs system Python**: UpApply venv has `httpx`, not `requests`. Use system Python for corpus scripts.
- **Profile endpoint is PUT not PATCH**: `seed_proposal_anchors.py` must GET the full profile, merge the new field, then PUT back.
- **Render auto-migrates**: `start.sh` runs `alembic upgrade head` on every deploy — no manual migration step needed.

---

## All Files Created/Modified

```
api/alembic/versions/012_add_proposal_anchors.py   NEW
api/app/models/user.py                              MODIFIED
api/app/schemas/job.py                              MODIFIED
api/app/schemas/profile.py                          MODIFIED
api/app/api/v1/jobs.py                              MODIFIED
api/app/services/cover_letter.py                    MODIFIED (major overhaul)
extension/src/lib/api-client.ts                     MODIFIED
extension/src/sidebar/store.ts                      MODIFIED
extension/src/sidebar/pages/Generator.tsx           MODIFIED
scripts/import_chatgpt_corpus.py                    NEW
scripts/chris_bio_memories.json                     NEW
scripts/chris_proposal_anchors.json                 NEW
scripts/seed_proposal_anchors.py                    NEW
docs/corpus-guided-cover-letters.md                 NEW
docs/SESSION_CONTEXT_2026-03-11.md                  NEW (this file)
CLAUDE.md                                           MODIFIED
```
