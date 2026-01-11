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

## Development Commands

### API Development

```bash
cd api

# Setup
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your DATABASE_URL and OPENAI_API_KEY

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000
```

### Extension Development

```bash
cd extension

# Install dependencies
npm install

# Development with hot reload
npm run dev

# Type checking
npm run type-check

# Production build
npm run build
# Load dist/ folder in chrome://extensions
```

### Testing

```bash
# API - check imports work
cd api && source venv/bin/activate
python -c "from app.main import app; print('OK')"

# Extension - type check
cd extension && npm run type-check
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
Personalized prompts built from user profile including:
- Professional identity and goals
- Tone preference
- Relevant memories (via semantic search)
- Skill emphasis

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
- `POST /api/v1/memories/bulk-import` - Import from resume

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
