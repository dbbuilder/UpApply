# Test Generation — 2026-04-12

## Baseline

| Suite | Before | After |
|-------|--------|-------|
| Non-DB (mocked) tests | 96 | 101 |
| DB integration tests | 0 (no local DB) | 0 |
| Extension specs | 0 | 0 |

## New Tests Added

### `/Users/admin/dev2/UpApply/api/tests/test_resume_parser.py` (5 tests)

All tests mock OpenAI calls — no external dependencies, run instantly.

| Test | Covers |
|------|--------|
| `test_parse_resume_happy_path` | Normal parse with structured result |
| `test_parse_resume_uses_correct_model` | Uses `settings.default_model` + `json_object` response format |
| `test_parse_resume_retries_on_failure` | tenacity retry decorator fires on transient error |
| `test_parse_resume_empty_text` | Empty/minimal resume doesn't crash |
| `test_parse_resume_includes_resume_text_in_prompt` | Resume text appended to user message |

**Result:** 5/5 pass

## Services Without Tests (deferred — SP > 2)

| Service | LOC | Gap | ID |
|---------|-----|-----|----|
| `text_extraction.py` | 221 | No test | TD-036 |
| `search_lab.py` | 242 | No test | TD-037 |

Both are > 150 LOC and involve complex multi-step logic (OCR, OpenAI, scoring). Tests would require significant mocking effort (3+ SP each). Deferred to Sprint 4.

## Extension Tests

No extension spec files exist. The extension code is primarily DOM manipulation and message-passing — difficult to unit test without a browser harness (jsdom or Playwright). Deferred.
