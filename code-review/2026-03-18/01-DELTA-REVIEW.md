# Delta Review: UpApply — 2026-03-18 vs 2026-02-18

## Review Continuity

| Field | Value |
|-------|-------|
| This review | 2026-03-18 |
| Prior review | 2026-02-18 (`code-review/2026-02-18/`) |
| Git window | 2026-02-18 → 2026-03-18 (~55 commits) |
| Prior rating | YELLOW |
| This rating | YELLOW |

## Summary of Changes

- **22 items resolved** since last review (all 16 sprint items + 6 backlog items)
- **2 items carried over** (TD-018 Generator.tsx, TD-022 version auto-increment)
- **11 new findings** identified across security, testing, code quality

---

## Resolved Items

| ID | Title | Resolution | Commit |
|----|-------|-----------|--------|
| TD-001 | API test suite (102 tests) | Added `tests/test_search_queries_api.py`, `test_search_query_model.py` | `e9e6e5e` series |
| TD-002 | Guard SECRET_KEY in prod | `field_validator` in config.py | `e9e6e5e` |
| TD-003 | Rate limit auth + feedback | `slowapi` on auth/feedback endpoints | `e9e6e5e` |
| TD-004 | Protect feedback list endpoint | Auth guard added | `e9e6e5e` |
| TD-005 | Wire attachment extraction E2E | Full background→content→API pipeline | `e9e6e5e` |
| TD-006 | GitHub Actions CI | `.github/workflows/ci.yml` | `e9e6e5e` |
| TD-007 | Sentry SDK wired | `api/app/main.py` reads `settings.sentry_dsn` | `e9e6e5e` |
| TD-008 | Extract analysis service | `job_analysis.py` service layer | `e9e6e5e` |
| TD-009 | Regenerate with feedback | Full regenerate flow in Generator.tsx | `e9e6e5e` |
| TD-010 | Application tracking | Queue tab, outcome recording | `f3d0e00` |
| TD-011 | Error states in extension | Loading/error states in store.ts | `e9e6e5e` |
| TD-012 | Shared TS types | `extension/src/types/index.ts` | `e9e6e5e` |
| TD-013 | Remove create_all from init_db | Removed from `database.py` | `e9e6e5e` |
| TD-014 | Loading states on secondary pages | Memories, skills, profile pages | `e9e6e5e` |
| TD-015 | Fix datetime.utcnow() | Replaced with `datetime.now(timezone.utc)` | `e9e6e5e` |
| TD-016 | Sanitize auth error messages | Generic messages in `auth.py` | `e9e6e5e` |
| TD-017 | Debug logging utility | `extension/src/lib/logger.ts` (DEV-only) | post-review |
| TD-019 | Proposal import UI | `ImportsTab.tsx` (353 lines, full import checklist) | `8bafc72` |
| TD-021 | Pin Docker Python | `FROM python:3.11.11-slim` | post-review |
| [new] | Queue tab | `QueuePage.tsx` — full pipeline states | `f3d0e00` |
| [new] | Search Labs (evaluate + optimize) | `search_queries.py:523–932` | `b1ea4d1` |
| [new] | Profile optimization engine | `profile_optimizer.py`, `/profile/optimize`, `OptimizePage.tsx` | `61aead8` |

---

## Carryover Items

| ID | Title | Priority | Notes |
|----|-------|----------|-------|
| TD-018 | Decompose Generator.tsx (1166 lines) | MEDIUM | No evidence of decomposition — same file, still 1166 lines |
| TD-022 | Auto-increment extension version | LOW | `manifest.json` still `1.0.0` hardcoded |

---

## New Findings

| ID | Title | Severity | Area |
|----|-------|----------|------|
| TD-023 | Raw exception exposed in /profile/optimize | MEDIUM | Security |
| TD-024 | No rate limit on 4 expensive AI endpoints | HIGH | Security |
| TD-025 | No anthropic_api_key production guard | LOW | Security |
| TD-026 | 62 console.logs in production builds | MEDIUM | Code Quality |
| TD-027 | content/index.ts at 2593 lines | MEDIUM | Architecture |
| TD-028 | search_queries.py at 932 lines — router+logic mixed | MEDIUM | Architecture |
| TD-029 | Test DB port 5435 → 41 tests fail locally | MEDIUM | Testing |
| TD-030 | conftest TRUNCATE missing job_reviews + work_logs | MEDIUM | Testing |
| TD-031 | No tests for profile_optimizer.py service | HIGH | Testing |
| TD-032 | test_cover_letter.py missing banned phrases tests | MEDIUM | Testing |
| TD-033 | No React ErrorBoundary in sidebar | HIGH | Quality |

---

## Coverage Change

| Area | Last Review | This Review | Trend |
|------|-------------|-------------|-------|
| API test count | 56 | 102 (61 pass locally, 41 need DB) | ↑ |
| Extension unit tests | 0 | 0 | → |
| E2E tests | 0 | 0 | → |
| Feature completeness | ~75% | ~88% | ↑ |
| New endpoints with rate limit | Auth/Feedback | Auth/Feedback only | → (3 new AI endpoints unprotected) |
| console.logs in prod builds | ~20 | ~113 total (content+bg+generator) | ↓ |
