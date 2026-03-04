# Testing Review: UpApply

| Field | Value |
|-------|-------|
| Date | 2026-02-18 |
| Reviewer | Chris Therriault |
| Rating | RED |

## Findings

### TST-001: Zero Test Files Exist

| Field | Value |
|-------|-------|
| Severity | CRITICAL |
| Location | Entire project |
| Status | Open |
| Effort | 13 SP |

**Risk:** There are **no test files** in the entire project. No unit tests, no integration tests, no end-to-end tests. The `pyproject.toml` lists `pytest` and `pytest-asyncio` as dev dependencies, but no tests exist. The extension has no test framework configured.

Testing verification was limited to:
- `python -c "from app.main import app; print('OK')"` (import check)
- `npm run type-check` (TypeScript compilation check)

**Recommendation:** Prioritize test coverage for critical paths:

**Sprint 1 - API Core (8 SP):**
- Auth: register, login, token validation, expired token handling
- Profile: CRUD operations, setup completion flow
- Job analysis: skill matching logic (pure function, easy to test)
- Cover letter generation: prompt building (mock OpenAI)

**Sprint 2 - API Integration (5 SP):**
- Memory CRUD with pgvector search
- Proposal CRUD and search
- Attachment extraction (mock file inputs)

**Extension tests are lower priority** since the UI is thin and most logic lives in the API.

---

### TST-002: No CI/CD Pipeline for Testing

| Field | Value |
|-------|-------|
| Severity | HIGH |
| Location | Project root (no `.github/workflows/`, no CI config) |
| Status | Open |
| Effort | 3 SP |

**Risk:** No automated testing on push or PR. Render auto-deploys from main, so any push goes straight to production without any verification beyond a successful Docker build.

**Recommendation:** Add a GitHub Actions workflow:
```yaml
on: [push, pull_request]
jobs:
  test-api:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
    steps:
      - run: pip install -e ".[dev]" && pytest
  test-extension:
    runs-on: ubuntu-latest
    steps:
      - run: npm ci && npm run type-check
```

---

### TST-003: Job Analysis Service is Highly Testable But Untested

| Field | Value |
|-------|-------|
| Severity | HIGH |
| Location | `api/app/services/job_analysis.py` |
| Status | Open |
| Effort | 3 SP |

**Risk:** The skill matching, deal breaker detection, and score calculation are pure functions (no I/O dependencies) that would be trivial to unit test. These are the core business logic of the product, yet have zero coverage.

**Recommendation:** This is the highest-ROI test target. Write tests for:
- `skills_match()` - exact matches, synonym matches, partial matches
- `check_deal_breakers()` - keyword avoidance, budget thresholds, client red flags
- `calculate_match_score()` - various skill/memory/dealbreaker combinations
- `generate_recommendation()` - score threshold behavior

---

### TST-004: Cover Letter Clean Function Untested

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `api/app/services/cover_letter.py:14-55` |
| Status | Open |
| Effort | 2 SP |

**Risk:** `clean_cover_letter()` removes salutations, signatures, and placeholders via regex. This is easy to break with edge cases and has no tests.

**Recommendation:** Write parameterized tests with various AI output formats:
- Letters starting with "Dear Hiring Manager"
- Letters ending with "Sincerely,\nJohn"
- Letters containing "[Your Name]" placeholders
- Letters that should pass through unchanged

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 2 |
| MEDIUM | 1 |
| LOW | 0 |
| **Total** | **4** |

The absence of tests is the single biggest risk in the project. The API's core business logic (skill matching, scoring, cover letter cleaning) is pure and highly testable. Starting with these would provide the highest ROI. A CI pipeline should be added alongside the first tests to prevent regression.
