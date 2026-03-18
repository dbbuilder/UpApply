# Technical Debt: UpApply — 2026-03-18

All items below are open. IDs continue from the prior review (last used: TD-022).

---

## CRITICAL — 0 items

No critical debt items.

---

## HIGH — 3 items (6 SP)

### TD-024: No rate limit on 4 expensive AI endpoints

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| HIGH | 2 | Security | `api/app/api/v1/search_queries.py:393,523,847`, `profile.py:212` |

`POST /search-queries/generate`, `POST /search-queries/evaluate`, `POST /search-queries/optimize`, and `POST /profile/optimize` all call GPT-4o or Claude with no rate limiting. A single user can repeatedly trigger these endpoints, exhausting API credits.

**Fix:** Add `@limiter.limit("5/hour")` to each. Pattern from `auth.py`.

---

### TD-031: No tests for `profile_optimizer.py`

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| HIGH | 2 | Testing | `api/app/services/profile_optimizer.py` |

No unit tests for the profile optimizer service. JSON parse failures, missing-field handling, and cache invalidation logic are untested. See 03-TESTING-GAPS.md § TST-003 for full test plan.

---

### TD-033: No React ErrorBoundary in extension sidebar

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| HIGH | 2 | Quality | `extension/src/sidebar/App.tsx` |

Any uncaught render exception crashes the entire sidebar to blank. An ErrorBoundary wrapper at the App level costs 30 min and prevents "the extension is broken" support requests.

---

## MEDIUM — 8 items (12.5 SP)

### TD-018: Decompose Generator.tsx (1,166 lines) [CARRYOVER]

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| MEDIUM | 5 | Architecture | `extension/src/sidebar/pages/Generator.tsx` |

Carried over from 2026-02-18. Generator.tsx remains a 1,166-line monolith. Planned decomposition: `CoverLetterPanel`, `AnalysisPanel`, `ScreeningPanel`, `JobHeader`. No regressions expected — pure component extraction.

---

### TD-023: Raw exception string in `/profile/optimize` HTTP response

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| MEDIUM | 0.5 | Security | `api/app/api/v1/profile.py:258` |

`detail=f"Profile optimization failed: {exc}"` leaks internal Anthropic error strings. Replace with a generic user-facing message and log the exception server-side.

---

### TD-026: 62+ `console.log` calls in production extension builds

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| MEDIUM | 2 | Quality | `extension/src/content/index.ts`, `background/index.ts` |

`logger.ts` exists but is not used in the two highest-log-volume files. Migrate to `logger.log()` / `logger.warn()` so production builds are silent.

---

### TD-027: `content/index.ts` at 2,593 lines

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| MEDIUM | 5 | Architecture | `extension/src/content/index.ts` |

Grew from ~1,600 to 2,593 lines since last review (new scraper paths for proposals, contracts, saved searches). Decomposition into `content/scoring.ts`, `content/scrapers/*.ts`, and a thin router in `content/index.ts` would significantly reduce complexity.

---

### TD-028: `search_queries.py` business logic inline in router (932 lines)

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| MEDIUM | 3 | Architecture | `api/app/api/v1/search_queries.py:523–932` |

The Search Labs evaluate + optimize logic (~400 lines) lives inside the router, making it untestable without HTTP. Extract to `api/app/services/search_lab.py`.

---

### TD-029: Test DB hardcoded to port 5435 — 41 tests fail locally

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| MEDIUM | 1 | Testing | `api/tests/conftest.py:21` |

Change fallback port from 5435 → 5432. See 03-TESTING-GAPS.md § TST-001.

---

### TD-030: `conftest.py` TRUNCATE missing `job_reviews` and `work_logs`

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| MEDIUM | 0.5 | Testing | `api/tests/conftest.py:68` |

Two tables added since the TRUNCATE was written are not included. Test isolation is broken for any test that touches those tables.

---

### TD-032: `test_cover_letter.py` missing banned phrases + `append_closing()` tests

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| MEDIUM | 1 | Testing | `api/tests/test_cover_letter.py` |

23 banned phrases, `append_closing()`, and `append_prototype_url()` are untested. A regression in any of these would silently ship. See 03-TESTING-GAPS.md § TST-004.

---

## LOW — 3 items (3.5 SP)

### TD-022: Extension version hardcoded at `1.0.0` [CARRYOVER]

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| LOW | 1 | Infrastructure | `extension/public/manifest.json` |

Auto-increment patch version on each build (via `vite.config.ts` or a `prebuild` npm script reading `package.json`).

---

### TD-025: No production guard for `anthropic_api_key`

| Priority | SP | Type | Files |
|----------|-----|------|-------|
| LOW | 0.5 | Security | `api/app/core/config.py:64` |

Add a startup warning (not a fatal raise) when `anthropic_api_key` is empty, so Render logs surface the gap clearly.

---

### OPS-01: Sentry DSN not set on Render

| Priority | SP | Type | Notes |
|----------|-----|------|-------|
| LOW | 1 | Operations | Non-code — create Sentry project, set `SENTRY_DSN` env var in Render dashboard. SDK is ready. |

---

## Backlog (Deferred / Nice-to-Have)

| ID | SP | Title | Why Deferred |
|----|-----|-------|-------------|
| TD-027 full | 5 | Decompose content/index.ts | Functional, not blocking |
| DIST-01 | 2 | Chrome Web Store submission | Needed for v1.0.0, not now |
| DOC-01 | 1 | User onboarding docs | Nice-to-have for beta |
| EXT-03 | 1 | DOM selector health monitoring | Defensive, low priority |
| DATA-01 | 2 | Geo tier config in profile settings | Hardcoded geo scores work fine |
| DATA-02 | 1 | Milestone row 3 selector verification | Low-frequency feature |

---

## Summary

| Priority | Count | SP |
|----------|-------|----|
| CRITICAL | 0 | 0 |
| HIGH | 3 | 6 |
| MEDIUM | 8 | 12.5 |
| LOW | 3 | 2.5 |
| Backlog | 6 | 12 |
| **Total actionable** | **11** | **21** |
