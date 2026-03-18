# Security & Quality: UpApply — 2026-03-18

## Status Since Last Review

All CRITICAL and HIGH security findings from 2026-02-18 are resolved:
- ✅ SECRET_KEY guard in production
- ✅ Rate limiting on auth endpoints (register, login)
- ✅ Rate limiting on feedback endpoints
- ✅ Feedback list endpoint now requires auth
- ✅ Auth error messages sanitized (generic "Invalid credentials")

New findings are MEDIUM/HIGH — no CRITICAL security issues introduced.

---

## Authentication & Authorization

### All new endpoints properly guarded ✅

Every route in `search_queries.py` (932 lines, 8 endpoints) uses `Depends(get_current_user)`. The new `/profile/optimize` endpoint is guarded. All user-scoped queries use `WHERE user_id = current_user.id` — no cross-user data leakage found.

---

## Input Validation

### No raw SQL injection risk ✅

All queries use SQLAlchemy ORM with parameterized statements. No `text()` with user-provided concatenation found in new code.

---

## Raw Exception Exposure

### TD-023: `/profile/optimize` leaks Anthropic/internal error detail

| Severity | File:Line | Effort |
|----------|-----------|--------|
| MEDIUM | `api/app/api/v1/profile.py:258` | 0.5 SP |

```python
# CURRENT — exposes internal exception string to API client
raise HTTPException(
    status_code=status.HTTP_502_BAD_GATEWAY,
    detail=f"Profile optimization failed: {exc}",   # ← leaks exc
)
```

Anthropic SDK exceptions can contain API keys, rate-limit details, or stack traces. Change to:

```python
raise HTTPException(
    status_code=status.HTTP_502_BAD_GATEWAY,
    detail="Profile optimization unavailable. Please try again later.",
)
```

Log the full `exc` via `logger.exception(...)` instead for server-side visibility.

---

## Rate Limiting

### TD-024: No rate limiting on expensive AI endpoints

| Severity | File:Line | Effort |
|----------|-----------|--------|
| HIGH | Multiple endpoints | 2 SP |

Four endpoints call OpenAI or Anthropic and have no rate limiting — a single user could exhaust API credits:

| Endpoint | AI Call | Cost per call |
|----------|---------|---------------|
| `POST /search-queries/generate` | GPT-4o (query gen) | ~$0.05 |
| `POST /search-queries/evaluate` | GPT-4o (lab suggestions) | ~$0.10 |
| `POST /search-queries/optimize` | GPT-4o (variant gen) | ~$0.10 |
| `POST /profile/optimize` | Claude sonnet-4-6 (full analysis) | ~$0.20 |

The 24h cache on `/profile/optimize` partially mitigates that one endpoint, but the Search Lab endpoints have no throttle.

**Fix:** Add `@limiter.limit("5/hour")` decorator on each. The `limiter` instance is already imported in the router via `app.core.rate_limit`. The pattern is established in `auth.py`.

---

## Secrets & Configuration

### TD-025: No production guard for `anthropic_api_key`

| Severity | File:Line | Effort |
|----------|-----------|--------|
| LOW | `api/app/core/config.py:64` | 0.5 SP |

`anthropic_api_key` defaults to `""`. If missing on Render, `/profile/optimize` will throw a raw `AuthenticationError` from the Anthropic SDK (caught by the HTTPException handler, but still an ungraceful failure). The `secret_key` has a `@field_validator` that raises on startup; `anthropic_api_key` does not.

Add a validator (warnings only — not all users need AI optimization):
```python
@field_validator("anthropic_api_key", mode="after")
def warn_missing_anthropic_key(cls, v: str, info) -> str:
    if not v:
        import warnings
        warnings.warn("ANTHROPIC_API_KEY not set — /profile/optimize will be unavailable")
    return v
```

---

## Code Quality

### TD-026: 62 `console.log` calls in production extension builds

| Severity | File:Line | Effort |
|----------|-----------|--------|
| MEDIUM | `extension/src/content/index.ts` (62), `background/index.ts` (39), `Generator.tsx` (6) | 2 SP |

`logger.ts` was created (TD-017 resolved) but never adopted. All 107 console calls across the three main extension files go to production. This:
- Leaks internal state (job URLs, titles, GraphQL responses) to any page with DevTools open
- Creates noise that makes real debugging harder
- Signals low production-readiness to security-conscious clients

The logger already supports `DEV`-only logging. Adoption across these three files is the remaining step.

**Priority:** Replace console.log calls in `content/index.ts` and `background/index.ts` with `logger.log()` / `logger.warn()`. `console.error` calls can stay (logger.error passes through always).

---

## File Size / Architecture

### TD-027: `content/index.ts` at 2,593 lines

| Severity | File:Line | Effort |
|----------|-----------|--------|
| MEDIUM | `extension/src/content/index.ts` | 5 SP |

The content script grew from ~1,600 to 2,593 lines since the last review. It now handles:
- Job tile extraction (notification, saved-jobs, find-work pages)
- Proposal list + detail scraping (active + archived)
- Contract scraping
- Saved jobs scraping
- Saved searches scraping
- Badge/chip injection + scoring pipeline
- GraphQL query execution
- MutationObserver management

Suggested decomposition into `content/` directory:
- `content/scoring.ts` — badge injection, chip rendering, notif/tile scoring pipeline
- `content/scrapers/proposals.ts` — proposal list + detail scraping
- `content/scrapers/contracts.ts` — contract scraping
- `content/scrapers/saved.ts` — saved jobs + saved searches
- `content/index.ts` — message router only (~200 lines)

### TD-028: `search_queries.py` router at 932 lines

| Severity | File:Line | Effort |
|----------|-----------|--------|
| MEDIUM | `api/app/api/v1/search_queries.py` | 3 SP |

The Search Labs evaluate + optimize logic (lines 523–932) contains ~400 lines of business logic (GPT calls, scoring algorithms, job coverage analysis) inline in the FastAPI router. This pattern makes it untestable without an HTTP client.

Suggested extraction: `api/app/services/search_lab.py` for `evaluate_coverage()`, `optimize_queries()`, and their GPT helper functions.
