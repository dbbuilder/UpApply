# Appendix A: File Inventory

| Field | Value |
|-------|-------|
| Date | 2026-02-18 |

## Project Statistics

| Metric | Value |
|--------|-------|
| API source files (Python) | 44 |
| API source LOC | ~6,046 |
| Extension source files (TS/TSX) | 22 |
| Extension source LOC | ~5,570 |
| Total source LOC | ~11,616 |
| Test files | 0 |
| Database migrations | 6 |
| SQLAlchemy models | 10 |
| API endpoints | ~35 |
| Extension pages | 7 |

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| API Framework | FastAPI | >=0.109.0 |
| Python | Python | 3.11 (Docker) / 3.14 (local) |
| ORM | SQLAlchemy | >=2.0.25 |
| Database | PostgreSQL + pgvector | 16 |
| Migrations | Alembic | >=1.13.0 |
| AI | OpenAI API | >=1.10.0 |
| Auth | python-jose + bcrypt | >=3.3.0 / >=4.1.0 |
| Extension UI | React + TypeScript | 18.2 / 5.3 |
| State Mgmt | Zustand | 4.4.7 |
| Build | Vite + CRXJS | 5.0 / 2.0.0-beta.23 |
| CSS | Tailwind CSS | 3.4.1 |
| Deployment | Render (Docker) | - |
| Extension | Chrome Manifest V3 | - |

## Key File Paths

### API Core
- Entry: `api/app/main.py`
- Config: `api/app/core/config.py`
- Database: `api/app/core/database.py`
- Security: `api/app/core/security.py`
- Embeddings: `api/app/core/embeddings.py`
- Router: `api/app/api/v1/__init__.py`

### API Endpoints
- Auth: `api/app/api/v1/auth.py`
- Profile: `api/app/api/v1/profile.py`
- Jobs: `api/app/api/v1/jobs.py`
- Memories: `api/app/api/v1/memories.py`
- Applications: `api/app/api/v1/applications.py`
- Proposals: `api/app/api/v1/proposals.py`
- Screening: `api/app/api/v1/screening_answers.py`
- Feedback: `api/app/api/v1/feedback.py`
- Beta Feedback: `api/app/api/v1/beta_feedback.py`

### API Services
- Job Analysis: `api/app/services/job_analysis.py`
- Cover Letter: `api/app/services/cover_letter.py`
- Text Extraction: `api/app/services/text_extraction.py`
- Resume Parser: `api/app/services/resume_parser.py`

### API Models
- User/Profile: `api/app/models/user.py`
- Job: `api/app/models/job.py`
- Memory: `api/app/models/memory.py`
- CoverLetter: `api/app/models/cover_letter.py`
- Application: `api/app/models/application.py`
- Proposal: `api/app/models/proposal.py`
- ScreeningAnswer: `api/app/models/screening_answer.py`
- Feedback: `api/app/models/feedback.py`
- BetaFeedback: `api/app/models/beta_feedback.py`

### Extension
- Background: `extension/src/background/index.ts`
- Content Script: `extension/src/content/index.ts`
- Selectors: `extension/src/content/upwork-selectors.ts`
- API Client: `extension/src/lib/api-client.ts`
- Storage: `extension/src/lib/storage.ts`
- State Store: `extension/src/sidebar/store.ts`
- App Root: `extension/src/sidebar/App.tsx`
- Generator: `extension/src/sidebar/pages/Generator.tsx`
- Auth: `extension/src/sidebar/pages/Auth.tsx`
- Setup: `extension/src/sidebar/pages/Setup.tsx`
- Memories: `extension/src/sidebar/pages/Memories.tsx`
- History: `extension/src/sidebar/pages/History.tsx`
- Analytics: `extension/src/sidebar/pages/Analytics.tsx`
- Beta Feedback: `extension/src/sidebar/pages/BetaFeedback.tsx`

### Deployment
- Render Config: `render.yaml`
- Dockerfile: `api/Dockerfile`
- Start Script: `api/start.sh`
- Manifest: `extension/public/manifest.json`

### Database Schema (via Alembic)
| Table | Key Columns |
|-------|-------------|
| users | id, email, hashed_password, is_active |
| user_profiles | ~40 columns (identity, goals, preferences, pricing, etc.) |
| memories | id, user_id, title, content, embedding (vector 1536), category |
| jobs | id, user_id, title, description, embedding, match_score, analysis |
| cover_letters | id, user_id, job_id, content, model_used, version |
| applications | id, user_id, job_id, status, bid_amount, earnings |
| feedback | id, user_id, feedback_type, rating, comment |
| screening_answers | id, user_id, question, answer, embedding |
| proposals | id, user_id, cover_letter_text, job_title, embedding, was_hired |
| beta_feedback | id, feedback_type, description, email |
