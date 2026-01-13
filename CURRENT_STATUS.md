# UpApply - Current Status

**Last Updated:** January 13, 2026
**Repository:** https://github.com/dbbuilder/UpApply

---

## Overview

UpApply is a Chrome Extension + FastAPI backend for AI-powered Upwork job applications. It generates personalized cover letters using semantic memory search (pgvector) and learns from your past successful proposals.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Chrome Extension                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │Content Script│  │ Background  │  │     Sidebar Panel       │  │
│  │(DOM Extract) │  │  Worker     │  │  (React + Zustand)      │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
└─────────┼────────────────┼─────────────────────┼────────────────┘
          │                │                     │
          └────────────────┴──────────┬──────────┘
                                      │ HTTPS
                          ┌───────────▼───────────┐
                          │   FastAPI on Render   │
                          │  - Cover Letter Gen   │
                          │  - Memory Search      │
                          │  - Job Analysis       │
                          │  - Text Extraction    │
                          └───────────┬───────────┘
                                      │
                          ┌───────────▼───────────┐
                          │ PostgreSQL + pgvector │
                          │  - Users & Profiles   │
                          │  - Memories (vectors) │
                          │  - Proposals          │
                          │  - Beta Feedback      │
                          └───────────────────────┘
```

---

## Recent Changes (January 13, 2026)

### 1. Full Job Posting Fetch with Attachment Extraction

**Commit:** `489e1eb` - Add full job posting fetch with attachment text extraction

When on an Upwork `/apply` page, users can now fetch the complete job posting from the "View job posting" link:

- Opens background tab to extract full description
- Downloads any attachments (preserves auth cookies)
- Sends to backend for text extraction:
  - **PDFs** via `pdfplumber`
  - **DOCX** via `python-docx`
  - **Images** via OpenAI Vision API (OCR)
- Stores extracted text in database (not original files)

**Files Changed:**
- `api/alembic/versions/005_add_attachment_fields.py` - Migration
- `api/app/services/text_extraction.py` - New extraction service
- `api/app/api/v1/jobs.py` - New endpoint
- `extension/src/background/index.ts` - Background tab management
- `extension/src/content/index.ts` - Job posting extraction
- `extension/src/sidebar/pages/Generator.tsx` - UI button

### 2. Beta Feedback System

**Commit:** `3da53fc` - Add beta feedback system for tester feedback collection

Simple feedback collection for beta testers:

- Feedback button in extension header (amber colored)
- 4 feedback types: Bug, Feature Request, Usability, General
- No authentication required to submit
- Auto-captures: page URL, browser info, extension version
- Optional email for follow-up

**Files Changed:**
- `api/alembic/versions/006_add_beta_feedback.py` - Migration
- `api/app/models/beta_feedback.py` - Model
- `api/app/api/v1/beta_feedback.py` - Endpoint
- `extension/src/sidebar/pages/BetaFeedback.tsx` - Feedback form

---

## Database Migrations

| Version | Description | Status |
|---------|-------------|--------|
| 001 | Initial schema (users, profiles, memories, jobs, etc.) | Applied |
| 002 | Add cover letter columns | Applied |
| 003 | Add preferred_closing field | Applied |
| 004 | Add screening_answers and proposals tables | Applied |
| 005 | Add attachment text fields to jobs | Deploying |
| 006 | Add beta_feedback table | Deploying |

---

## API Endpoints

### Core Endpoints
```
Auth:
  POST /api/v1/auth/register
  POST /api/v1/auth/login
  GET  /api/v1/auth/me

Profile:
  GET  /api/v1/profile
  PUT  /api/v1/profile
  POST /api/v1/profile/import-resume

Memories:
  GET  /api/v1/memories
  POST /api/v1/memories
  POST /api/v1/memories/search

Jobs:
  POST /api/v1/jobs/analyze
  POST /api/v1/jobs/{id}/extract-attachments  (NEW)

Cover Letters:
  POST /api/v1/jobs/cover-letters/generate

Proposals:
  POST /api/v1/proposals
  POST /api/v1/proposals/search
  POST /api/v1/proposals/import-from-upwork

Beta Feedback:
  POST /api/v1/beta-feedback  (NEW - no auth required)
  GET  /api/v1/beta-feedback  (NEW - list all feedback)
```

---

## Deployment

### API (Render)
- **URL:** https://upapply-api.onrender.com
- **Health:** https://upapply-api.onrender.com/health
- **Auto-deploy:** Yes (from main branch)
- **Database:** PostgreSQL 16 with pgvector

### Extension
- **Distribution:** Manual (ZIP file)
- **Current Version:** 1.0.0
- **Build:** `cd extension && npm run build`
- **Package:** `upapply-extension-v1.0.0.zip`

---

## Extension Features

### Main Sidebar Sections
1. **Generator** - Job analysis, cover letter generation, fill functionality
2. **Memories** - Add/edit work experiences for semantic search
3. **Stats** - Analytics dashboard with success rates
4. **Feedback** - Beta feedback submission

### Generator Page Features
- Job detection from Upwork pages
- "Fetch full job posting & attachments" button
- Match score analysis
- Cover letter generation with relevant memories
- Screening question assistance with past answers
- Auto-fill cover letter and bid amount

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI, SQLAlchemy 2.0 async, Pydantic |
| Database | PostgreSQL 16 + pgvector |
| AI | OpenAI (embeddings, GPT-4o for generation and OCR) |
| Frontend | React 18, TypeScript, Vite |
| State | Zustand |
| Styling | Tailwind CSS |
| Extension | Chrome Manifest V3, Side Panel API |
| PDF Extraction | pdfplumber |
| DOCX Extraction | python-docx |

---

## File Structure

```
UpApply/
├── api/                          # FastAPI backend
│   ├── app/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── core/                # Config, DB, security, embeddings
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── api/v1/              # Route handlers
│   │   └── services/            # Business logic (incl. text_extraction.py)
│   ├── alembic/                 # Database migrations (001-006)
│   ├── Dockerfile
│   └── pyproject.toml
├── extension/                    # Chrome extension
│   ├── public/
│   │   ├── manifest.json
│   │   └── icons/
│   ├── src/
│   │   ├── background/          # Service worker
│   │   ├── content/             # DOM extraction
│   │   ├── sidebar/             # React UI
│   │   │   └── pages/           # Generator, Memories, Analytics, BetaFeedback
│   │   └── lib/                 # API client, storage
│   └── vite.config.ts
├── render.yaml                   # Render deployment config
├── CLAUDE.md                     # Development guide
├── PROJECT_STATUS.md             # Detailed project status
└── CURRENT_STATUS.md             # This file
```

---

## Tester Onboarding

### Installation
1. Download `upapply-extension-v1.0.0.zip`
2. Unzip to a folder
3. Go to `chrome://extensions`
4. Enable Developer mode
5. Click "Load unpacked" → select folder

### First-Time Setup
1. Register account
2. Complete profile wizard
3. Add memories (work experiences)
4. Navigate to Upwork job page

### Testing Checklist
- [ ] Job detection works on `/apply` pages
- [ ] "Fetch full job posting" extracts data
- [ ] Attachments are detected and processed
- [ ] Cover letter generation uses relevant memories
- [ ] Fill functionality works
- [ ] Feedback submission works

### Submitting Feedback
Click **Feedback** in header → select type → describe → submit

---

## Viewing Beta Feedback

```bash
# All feedback
curl https://upapply-api.onrender.com/api/v1/beta-feedback | jq

# Filter by type
curl "https://upapply-api.onrender.com/api/v1/beta-feedback?feedback_type=bug" | jq
```

---

## Next Steps

1. **Monitor beta feedback** for bugs and feature requests
2. **Test attachment extraction** with various file types
3. **Improve cover letter quality** based on user feedback
4. **Consider Chrome Web Store** submission for easier distribution
5. **Add more analytics** on proposal success rates

---

## Contact

- **Repository:** https://github.com/dbbuilder/UpApply
- **Issues:** https://github.com/dbbuilder/UpApply/issues
