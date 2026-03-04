# Technical Debt Backlog: UpApply

| Field | Value |
|-------|-------|
| Date | 2026-02-18 |
| Reviewer | Chris Therriault |
| Total Debt | ~82 SP |

## Priority: CRITICAL

### TD-001: Add Core API Tests

| Field | Value |
|-------|-------|
| Priority | CRITICAL |
| Story Points | 13 |
| Type | Testing |
| Source | TST-001, TST-003 |
| Files | `api/tests/` (new) |

**Description:** Create test suite for API core: auth, profile, job analysis, cover letter generation.

**Acceptance Criteria:**
- [ ] Auth tests: register, login, token validation, expired tokens
- [ ] Job analysis pure functions: skill matching, deal breakers, scoring
- [ ] Cover letter clean function with edge cases
- [ ] Profile CRUD operations
- [ ] pytest runs successfully with `pytest api/tests/`

---

### TD-002: Validate SECRET_KEY in Production

| Field | Value |
|-------|-------|
| Priority | CRITICAL |
| Story Points | 0.5 |
| Type | Security |
| Source | SEC-001 |
| Files | `api/app/core/config.py` |

**Description:** Add runtime validation that SECRET_KEY is not the default value in production.

**Acceptance Criteria:**
- [ ] App refuses to start if SECRET_KEY is default and environment=production
- [ ] Log warning in development mode

---

## Priority: HIGH

### TD-003: Add Rate Limiting to Auth + Feedback Endpoints

| Field | Value |
|-------|-------|
| Priority | HIGH |
| Story Points | 3 |
| Type | Security |
| Source | SEC-003, SEC-004 |
| Files | `api/app/main.py`, `api/app/api/v1/auth.py`, `api/app/api/v1/beta_feedback.py` |

**Description:** Add IP-based rate limiting using `slowapi` to prevent brute-force attacks and feedback spam.

**Acceptance Criteria:**
- [ ] Login: 5 attempts/min/IP
- [ ] Register: 3 attempts/min/IP
- [ ] Beta feedback: 10 submissions/hr/IP
- [ ] Return 429 with Retry-After header

---

### TD-004: Protect Beta Feedback List Endpoint

| Field | Value |
|-------|-------|
| Priority | HIGH |
| Story Points | 1 |
| Type | Security |
| Source | SEC-005 |
| Files | `api/app/api/v1/beta_feedback.py` |

**Description:** Add authentication requirement to the GET feedback list endpoint.

**Acceptance Criteria:**
- [ ] GET /beta-feedback requires valid auth token
- [ ] Or: remove endpoint entirely and query DB directly

---

### TD-005: Wire Attachment Extraction End-to-End

| Field | Value |
|-------|-------|
| Priority | HIGH |
| Story Points | 3 |
| Type | Feature |
| Source | FC-001 |
| Files | `extension/src/sidebar/pages/Generator.tsx` |

**Description:** Complete the attachment extraction pipeline: create job first, then extract attachments, then use enriched data for analysis.

**Acceptance Criteria:**
- [ ] Extension creates/saves job via POST /jobs before attachment extraction
- [ ] Downloaded attachments sent to POST /jobs/{id}/extract-attachments
- [ ] Extracted text used in subsequent analysis and cover letter generation
- [ ] UI shows extraction progress and status

---

### TD-006: Add CI Pipeline with Tests

| Field | Value |
|-------|-------|
| Priority | HIGH |
| Story Points | 3 |
| Type | Infra |
| Source | TST-002 |
| Files | `.github/workflows/ci.yml` (new) |

**Description:** Add GitHub Actions workflow that runs tests and type-checking on push/PR.

**Acceptance Criteria:**
- [ ] API tests run with PostgreSQL + pgvector service
- [ ] Extension type-check runs
- [ ] Pipeline blocks merge on failure

---

### TD-007: Add Error Tracking (Sentry)

| Field | Value |
|-------|-------|
| Priority | HIGH |
| Story Points | 2 |
| Type | Infra |
| Source | INFRA-002 |
| Files | `api/app/main.py`, `api/pyproject.toml` |

**Description:** Set up Sentry error tracking for the API.

**Acceptance Criteria:**
- [ ] Sentry project created
- [ ] SDK integrated in FastAPI
- [ ] Unhandled exceptions captured with context
- [ ] OpenAI API errors tagged

---

## Priority: MEDIUM

### TD-008: Extract Job Analysis Into Service Function

| Field | Value |
|-------|-------|
| Priority | MEDIUM |
| Story Points | 5 |
| Type | Quality |
| Source | ARCH-001 |
| Files | `api/app/api/v1/jobs.py`, `api/app/services/job_analysis.py` |

**Description:** Consolidate the duplicated analysis pipeline into a single `run_full_analysis()` function.

**Acceptance Criteria:**
- [ ] Single function for skill match + memories + deal breakers + score
- [ ] All 4 endpoints use the consolidated function
- [ ] No behavior change

---

### TD-009: Add Cover Letter Regeneration with Feedback in Extension

| Field | Value |
|-------|-------|
| Priority | MEDIUM |
| Story Points | 3 |
| Type | Feature |
| Source | FC-002 |
| Files | `extension/src/sidebar/pages/Generator.tsx`, `extension/src/sidebar/store.ts` |

**Description:** Wire the regenerate endpoint with feedback input instead of generating fresh each time.

**Acceptance Criteria:**
- [ ] "Regenerate" shows a feedback text field
- [ ] Calls POST /cover-letters/{id}/regenerate with feedback
- [ ] Shows new version with ability to go back

---

### TD-010: Connect Application Tracking to UI

| Field | Value |
|-------|-------|
| Priority | MEDIUM |
| Story Points | 5 |
| Type | Feature |
| Source | FC-003, FC-004 |
| Files | `extension/src/sidebar/pages/Generator.tsx`, `extension/src/sidebar/pages/History.tsx` |

**Description:** After filling a cover letter, prompt user to mark job as applied. Add outcome tracking to History page.

**Acceptance Criteria:**
- [ ] "Mark as Applied" prompt after Fill action
- [ ] History page shows applications with status
- [ ] Outcome recording UI (hired, declined, no response)
- [ ] Analytics page shows meaningful data

---

### TD-011: Add Error States to Extension UI

| Field | Value |
|-------|-------|
| Priority | MEDIUM |
| Story Points | 3 |
| Type | UX |
| Source | UX-002, FC-007 |
| Files | `extension/src/sidebar/store.ts`, `extension/src/sidebar/pages/Generator.tsx` |

**Description:** Show error messages when API calls fail, with retry option. Handle cold-start and network failures.

**Acceptance Criteria:**
- [ ] Error state in store for each async operation
- [ ] Error card component with retry button
- [ ] "Connecting to server..." state on first 502/503
- [ ] Network failure detection

---

### TD-012: Share TypeScript Types Across Extension Contexts

| Field | Value |
|-------|-------|
| Priority | MEDIUM |
| Story Points | 2 |
| Type | Quality |
| Source | ARCH-003 |
| Files | `extension/src/types/index.ts` (new), content/index.ts, background/index.ts, store.ts |

**Description:** Create shared type definitions for JobData, ScreeningQuestion, etc.

**Acceptance Criteria:**
- [ ] Single `types/index.ts` with all shared interfaces
- [ ] All 3 contexts import from shared types
- [ ] No duplicate interface definitions

---

### TD-013: Remove create_all from init_db

| Field | Value |
|-------|-------|
| Priority | MEDIUM |
| Story Points | 1 |
| Type | Quality |
| Source | ARCH-006 |
| Files | `api/app/core/database.py` |

**Description:** Remove `Base.metadata.create_all` from startup. Rely on Alembic only.

**Acceptance Criteria:**
- [ ] `init_db()` only creates pgvector extension
- [ ] All schema management via Alembic
- [ ] Deploy succeeds with change

---

### TD-014: Add Loading States to Secondary Pages

| Field | Value |
|-------|-------|
| Priority | MEDIUM |
| Story Points | 2 |
| Type | UX |
| Source | UX-001 |
| Files | Memories.tsx, History.tsx, Analytics.tsx |

**Description:** Add loading indicators when fetching data on secondary pages.

**Acceptance Criteria:**
- [ ] Loading skeleton/spinner on each page
- [ ] Consistent with Generator page patterns

---

### TD-015: Fix datetime.utcnow() Deprecation

| Field | Value |
|-------|-------|
| Priority | MEDIUM |
| Story Points | 1 |
| Type | Quality |
| Source | CQ-001 |
| Files | `api/app/api/v1/jobs.py` |

**Description:** Replace deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)`.

**Acceptance Criteria:**
- [ ] All occurrences updated
- [ ] No naive datetime usage

---

### TD-016: Sanitize Error Messages Returned to Clients

| Field | Value |
|-------|-------|
| Priority | MEDIUM |
| Story Points | 1 |
| Type | Security |
| Source | SEC-006 |
| Files | `api/app/api/v1/auth.py` |

**Description:** Remove internal exception details from error responses.

**Acceptance Criteria:**
- [ ] Generic error messages in HTTP responses
- [ ] Detailed errors only in server logs

---

## Priority: LOW

### TD-017: Add Debug Logging Utility to Extension

| Field | Value |
|-------|-------|
| Priority | LOW |
| Story Points | 1 |
| Type | Quality |
| Source | CQ-005 |
| Files | `extension/src/lib/logger.ts` (new) |

**Description:** Replace console.log with a debug-gated logger.

---

### TD-018: Decompose Generator.tsx

| Field | Value |
|-------|-------|
| Priority | LOW |
| Story Points | 5 |
| Type | Quality |
| Source | CQ-006 |
| Files | `extension/src/sidebar/pages/Generator.tsx` |

**Description:** Split into sub-components: JobInfoCard, MatchAnalysis, CoverLetterPanel, ScreeningQuestions.

---

### TD-019: Add Proposal Import UI

| Field | Value |
|-------|-------|
| Priority | LOW |
| Story Points | 3 |
| Type | Feature |
| Source | FC-005 |
| Files | Extension sidebar |

**Description:** Add button to import past proposals from Upwork's My Proposals page.

---

### TD-020: Cover Letter Clean Function Tests

| Field | Value |
|-------|-------|
| Priority | LOW |
| Story Points | 2 |
| Type | Testing |
| Source | TST-004 |
| Files | `api/tests/test_cover_letter.py` (new) |

**Description:** Parameterized tests for `clean_cover_letter()`.

---

### TD-021: Pin Docker Python Version

| Field | Value |
|-------|-------|
| Priority | LOW |
| Story Points | 0.5 |
| Type | Infra |
| Source | INFRA-004 |
| Files | `api/Dockerfile` |

---

### TD-022: Auto-Increment Extension Version

| Field | Value |
|-------|-------|
| Priority | LOW |
| Story Points | 1 |
| Type | Infra |
| Source | INFRA-006 |
| Files | Build scripts |

---

## Sprint Allocation

| Sprint | Items | Story Points |
|--------|-------|-------------|
| Sprint 1: Critical | TD-001, TD-002 | 13.5 |
| Sprint 2: Security & CI | TD-003, TD-004, TD-006, TD-007, TD-016 | 10 |
| Sprint 3: Features | TD-005, TD-009, TD-010 | 11 |
| Sprint 4: Quality & UX | TD-008, TD-011, TD-012, TD-013, TD-014, TD-015 | 14 |
| Backlog | TD-017 through TD-022 | 12.5 |
| **Total** | **22 items** | **~61 SP** |
