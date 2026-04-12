# Sprint Plan — 2026-04-12

Prior review: 2026-03-18 | All 3 sprints: RESOLVED
Current state: GREEN | Total deferred: ~13 SP

---

## Sprint 4: Test Completion (8 SP) — NEXT

| ID | SP | Title | File | Type |
|----|----|----|------|------|
| TD-036 | 3 | Tests for text_extraction.py | `tests/test_text_extraction.py` (new) | TST |
| TD-037 | 3 | Tests for search_lab.py | `tests/test_search_lab.py` (new) | TST |
| TD-035 | 2 | Document/resolve 41 DB-dependent test errors on local dev | `tests/conftest.py` | TST |

**Notes:**
- `text_extraction.py` uses `pytesseract` and `PIL` — mock both
- `search_lab.py` calls OpenAI for scoring/optimization — mock the client
- TD-035: the 41 DB errors are expected on machines without a local PostgreSQL — consider adding a `pytest.ini` marker to skip them gracefully (`@pytest.mark.requires_db`)

---

## Sprint 5: Distribution (3 SP) — AFTER SPRINT 4

| ID | SP | Title | Notes |
|----|----|----|-------|
| DIST-01 | 2 | Chrome Web Store submission | Requires screenshots, description, icons |
| DOC-01 | 1 | User onboarding docs | Simple setup guide |

---

## Backlog (post v1.0.0)

| ID | SP | Title |
|----|----|-------|
| EXT-03 | 1 | DOM selector health monitoring (EXT-03 stubs exist in content/index.ts) |
| DATA-01 | 2 | Geo tier config in profile settings |
| DATA-02 | 1 | Milestone row 3 selector verification |
| EXT-02 | 2 | was_hired backfill (re-run import with fixed NUXT path) |

---

## Completed This Review (2026-04-12)

- [x] **TD-034** (0.5 SP): Migrate console.log → logger in draft-saver.ts
- [x] **TST-NEW** (1 SP): test_resume_parser.py — 5 tests, all passing
