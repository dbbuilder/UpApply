# Architecture Review: UpApply

| Field | Value |
|-------|-------|
| Date | 2026-02-18 |
| Reviewer | Chris Therriault |
| Rating | GREEN |

## Findings

### ARCH-001: Significant Code Duplication in Job Analysis Flow

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `api/app/api/v1/jobs.py:64-128`, `131-236`, `283-352`, `379-561` |
| Status | Open |
| Effort | 5 SP |

**Risk:** The job analysis pipeline (skill matching, memory search, deal breaker checks, score calculation) is duplicated 4 times across `analyze_job`, `create_job`, `get_job_match`, and `generate_cover_letter_endpoint`. Any change to the analysis logic must be replicated in 4 places.

**Recommendation:** Extract a single `run_full_analysis(db, user, profile, job_data)` service function that all endpoints call. This also reduces the endpoint handler length from 100+ lines to ~20.

---

### ARCH-002: Database Session Auto-Commit Pattern

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `api/app/core/database.py:32-42` |
| Status | Open |
| Effort | 3 SP |

**Code:**
```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**Risk:** The session auto-commits after every request, even read-only ones. Some endpoints also call `await db.commit()` explicitly (e.g., `jobs.py:233`), resulting in double-commits. While not harmful, it creates confusion about who owns the commit lifecycle.

**Recommendation:** Remove the auto-commit from `get_db()` and make commits explicit in write operations only. This makes the transaction boundaries clearer and prevents accidental data persistence on GET requests.

---

### ARCH-003: JobData Interface Duplicated Across 4 Files

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `extension/src/content/index.ts:18-34`, `extension/src/sidebar/store.ts:7-28`, `extension/src/background/index.ts:7-24` |
| Status | Open |
| Effort | 2 SP |

**Risk:** The `JobData` interface is defined 3 times with slightly different shapes. The content script version includes `screeningQuestions`, the background version doesn't. This can cause silent data loss when passing between contexts.

**Recommendation:** Create a shared `extension/src/types/index.ts` with all shared interfaces. Import from there in all three contexts.

---

### ARCH-004: No API Versioning Strategy Beyond v1 Prefix

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `api/app/api/v1/__init__.py` |
| Status | Open |
| Effort | 0.5 SP |

**Risk:** The `/api/v1` prefix is in place, which is good. But there's no version negotiation, deprecation header strategy, or documentation of what constitutes a breaking change. With only one extension version in the wild and few users, this is fine for now.

**Recommendation:** Document the versioning approach in CLAUDE.md. No code changes needed yet.

---

### ARCH-005: Extension Uses window.open() for Cover Letter Editor

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `extension/src/sidebar/pages/Generator.tsx:110-168` |
| Status | Open |
| Effort | 3 SP |

**Code:**
```typescript
const popup = window.open('', 'CoverLetterEditor', ...);
popup.document.write(`<!DOCTYPE html>...`);
```

**Risk:** The popup editor injects raw HTML via `document.write()`. While the cover letter content is HTML-escaped (`replace(/</g, '&lt;')`), this approach is fragile. The popup also uses `window.opener.postMessage()` without origin validation.

**Recommendation:** For beta, this works fine. Eventually, move to a proper extension popup page (`editor.html`) or an inline expandable editor. Add origin check on `postMessage`.

---

### ARCH-006: Both Alembic Migrations and SQLAlchemy create_all Run at Startup

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `api/app/core/database.py:45-51`, `api/start.sh:15` |
| Status | Open |
| Effort | 2 SP |

**Code:**
```python
async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
```

And `start.sh`:
```bash
alembic upgrade head
```

**Risk:** Alembic runs migrations first, then the app starts and `Base.metadata.create_all` runs again. If a migration adds a column, but the model is ahead of the migration, `create_all` could silently add columns that Alembic doesn't know about, causing migration chain drift.

**Recommendation:** Remove `Base.metadata.create_all` from `init_db()`. Rely solely on Alembic for schema management. Keep only the pgvector extension creation.

---

### ARCH-007: Raw SQL Used for Vector Operations Instead of SQLAlchemy ORM

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `api/app/services/job_analysis.py:120-130`, `api/app/api/v1/memories.py:189-201` |
| Status | Open |
| Effort | 0.5 SP |

**Risk:** Raw SQL text queries are used for pgvector similarity search. This works but bypasses SQLAlchemy's type safety and query builder. pgvector-python has ORM-compatible operators.

**Recommendation:** Low priority. The raw SQL is clear, well-structured, and parameterized. Could migrate to `pgvector.sqlalchemy` operators later but not necessary.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 4 |
| LOW | 3 |
| **Total** | **7** |

The architecture is clean and well-structured. The FastAPI backend follows good patterns (dependency injection, Pydantic schemas, async SQLAlchemy). The extension has a good separation between content script, background worker, and sidebar UI. The main debt items are code duplication in the analysis flow and duplicate type definitions in the extension.
