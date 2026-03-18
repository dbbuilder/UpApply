# Testing Gaps: UpApply — 2026-03-18

## Coverage Map

| Module | Unit Tests | Integration | CI | Priority |
|--------|-----------|------------|-----|----------|
| `auth.py` | ✅ | ✅ | ✅ | — |
| `profile.py` | ✅ | ✅ | ✅ | — |
| `job_analysis.py` | ✅ | ✅ | ✅ | — |
| `cover_letter.py` | ✅ partial | ❌ | ✅ | HIGH |
| `search_queries.py` API | ✅ (41 tests) | ✅ CI only | ❌ locally | MEDIUM |
| `profile_optimizer.py` | ❌ | ❌ | ❌ | HIGH |
| `search_lab` (evaluate/optimize logic) | ❌ | ❌ | ❌ | MEDIUM |
| Extension components | ❌ | ❌ | ❌ | LOW |
| Extension content script | ❌ | ❌ | ❌ | LOW |

**Total API tests:** 102 (61 unit pass locally; 41 integration tests require DB at port 5435)

---

## Missing / Broken Test Suites

### TST-001 / TD-029: `test_search_queries_api.py` tests fail locally (port 5435)

| Severity | File:Line | Effort |
|----------|-----------|--------|
| MEDIUM | `api/tests/conftest.py:21` | 1 SP |

The `conftest.py` hardcodes the fallback test DB to `localhost:5435/upapply_test`. In CI the env var `TEST_DATABASE_URL` is set to port 5432. Locally, without Docker running at port 5435, all 41 integration tests error at setup with `OSError: Multiple exceptions: [Errno 61] Connect call failed`.

This creates a broken local dev experience — all 41 search query tests appear to fail when they're actually just misconfigured. In CI they pass correctly.

**Fix:** Change default fallback to `localhost:5432/upapply_test` (the standard PostgreSQL port) so local devs don't need a non-standard port. Document a `make test-db` or `docker run` command in the README for local integration tests.

```python
# conftest.py:21 — change default port from 5435 to 5432
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://upapply:upapply@localhost:5432/upapply_test",
)
```

---

### TST-002 / TD-030: `conftest.py` TRUNCATE missing `job_reviews` and `work_logs`

| Severity | File:Line | Effort |
|----------|-----------|--------|
| MEDIUM | `api/tests/conftest.py:68` | 0.5 SP |

The TRUNCATE after each test covers:
```
beta_feedback, feedback, screening_answers, proposals,
applications, cover_letters, jobs, search_queries, memories,
user_profiles, users
```

Missing: `job_reviews`, `work_logs`. Any test that creates job_review or work_log records bleeds into subsequent tests, potentially causing false passes or confusing failures.

**Fix:**
```python
"TRUNCATE TABLE beta_feedback, feedback, screening_answers, proposals, "
"applications, cover_letters, jobs, search_queries, memories, "
"job_reviews, work_logs, "  # add these
"user_profiles, users RESTART IDENTITY CASCADE"
```

---

### TST-003 / TD-031: No tests for `profile_optimizer.py`

| Severity | File:Line | Effort |
|----------|-----------|--------|
| HIGH | `api/app/services/profile_optimizer.py` | 2 SP |

`profile_optimizer.py` is the most complex new service (212 lines). It:
- Builds a structured profile prompt
- Makes an Anthropic API call
- Parses a complex JSON response into `ProfileOptimizeResponse`
- The JSON parse can fail silently (falls back to empty response)

Zero tests exist for:
- Prompt construction (does it handle missing fields correctly?)
- Response parsing (does malformed JSON raise cleanly?)
- Caching behavior (does `force_refresh=True` bypass cache?)
- Empty profile edge cases

Suggested `api/tests/test_profile_optimizer.py`:
```python
def test_optimize_with_empty_profile():
    """Should not throw on missing title/bio/skills."""

def test_optimize_prompt_contains_key_sections():
    """Prompt should include bio length, skills count, rate."""

def test_optimize_response_parsing():
    """Should parse valid response JSON into ProfileOptimizeResponse."""

def test_optimize_cache_returned_when_fresh():
    """Should return cached result if < 24h old and force_refresh=False."""

def test_optimize_force_refresh_bypasses_cache():
    """Should call AI again when force_refresh=True."""
```

Use monkeypatching/mocking for the Anthropic client to avoid live API calls in tests.

---

### TST-004 / TD-032: `test_cover_letter.py` incomplete — banned phrases not tested

| Severity | File:Line | Effort |
|----------|-----------|--------|
| MEDIUM | `api/tests/test_cover_letter.py` | 1 SP |

`test_cover_letter.py` has 10 tests covering basic salutation/sign-off removal. Missing:

1. **23 banned phrases** — e.g. "passionate", "I am writing to", "I would be a great fit", "leverage", "unique opportunity" — none are tested to confirm `clean_cover_letter()` removes or flags them
2. **`append_closing()` tests** — not tested at all
3. **`append_prototype_url()` tests** — not tested at all
4. **"I" sentence start rule** — the core cover letter rule ("No sentence may begin with I") is not validated by the clean function but should be tested at the generation level

`append_closing()` behavior is critical to the cover letter format — if it breaks, every cover letter loses "Warm regards," with no test catching it.
