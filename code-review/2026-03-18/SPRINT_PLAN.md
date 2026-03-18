# Sprint Plan: UpApply
**Date:** 2026-03-18
**Based on:** `code-review/2026-03-18/` + `docs/ROADMAP-2026-03-17.md`
**Total remaining:** ~21 SP (actionable) + 12 SP (backlog) across 3 sprints

---

## Product Completion Status

| Area | Status | Gaps |
|------|--------|------|
| Core features | ~88% complete | 1 MISSING (saved jobs badges), 3 PARTIAL |
| Test coverage | 102 API tests (61 run locally) | profile_optimizer untested, conftest broken |
| Security | 1 HIGH, 1 MEDIUM open | Rate limits on AI endpoints |
| Tech debt | 21 SP open | Generator.tsx, content/index.ts decomposition |

---

## Sprint 1: Security + Test Foundations (~9 SP)

**Goal:** No unguarded AI endpoints in production; critical test infrastructure fixed; ErrorBoundary prevents blank-sidebar crashes.

**Definition of Done:**
- [ ] 4 AI endpoints have `@limiter.limit("5/hour")`
- [ ] `/profile/optimize` returns generic error message (no raw exc)
- [ ] `npm run type-check` and all tests pass
- [ ] conftest TRUNCATE includes job_reviews + work_logs
- [ ] Test DB port is 5432 (all 102 tests pass locally with DB running)
- [ ] `profile_optimizer.py` has mocked unit tests covering: empty profile, parse error, cache behavior
- [ ] ErrorBoundary wraps the sidebar root

**Items:**

| ID | Title | SP | Type | Files |
|----|-------|----|------|-------|
| TD-024 | Rate limit AI endpoints (5/hr each) | 2 | Security | `search_queries.py:393,523,847`; `profile.py:212` |
| TD-023 | Sanitize /profile/optimize error detail | 0.5 | Security | `profile.py:258` |
| TD-033 | Add React ErrorBoundary to sidebar | 2 | Quality | `App.tsx` (new `ErrorBoundary.tsx`) |
| TD-031 | Tests for profile_optimizer.py | 2 | Testing | `tests/test_profile_optimizer.py` (new) |
| TD-029 | Fix test DB port 5435 → 5432 | 1 | Testing | `tests/conftest.py:21` |
| TD-030 | Add job_reviews + work_logs to TRUNCATE | 0.5 | Testing | `tests/conftest.py:68` |
| TD-032 | Cover letter banned phrases + append tests | 1 | Testing | `tests/test_cover_letter.py` |

**Sprint 1 notes:** TD-024 uses the existing `limiter` instance from `app.core.rate_limit` — it's a decorator addition only. TD-023 and TD-029/030 are one-liners. The hardest item is TD-031 (profile_optimizer mocked tests).

---

## Sprint 2: Feature + Quality (~8 SP)

**Goal:** Saved jobs page shows score badges; console.logs stripped from production builds; cover letter system fully tested.

**Definition of Done:**
- [ ] Score badges appear on `/nx/search/jobs/saved/` within 2s of page load
- [ ] MutationObserver on `article[data-test="JobTile"]` fires correctly
- [ ] No regression on notification bell scoring
- [ ] `content/index.ts` and `background/index.ts` use `logger.log()` not `console.log()`
- [ ] Production build has 0 `console.log` calls in extension JS

**Items:**

| ID | Title | SP | Type | Files |
|----|-------|----|------|-------|
| EXT-01 | Saved jobs page badge scorer | 3 | Feature | `extension/src/content/index.ts` |
| TD-026 | Migrate console.logs to logger | 2 | Quality | `content/index.ts`, `background/index.ts` |
| TD-025 | anthropic_api_key startup warning | 0.5 | Security | `api/app/core/config.py:64` |
| OPS-01 | Sentry DSN on Render | 1 | Operations | Render dashboard only (non-code) |
| TD-022 | Auto-increment extension version | 1 | Infrastructure | `manifest.json` + build script |

**Sprint 2 notes:** EXT-01 has a complete implementation plan in `/Users/admin/.claude/plans/zesty-booping-frog.md` — it's ~80 lines in `content/index.ts`. OPS-01 is a non-code Render dashboard task. TD-026 is find-and-replace across 100 lines.

---

## Sprint 3: Architecture Refactor (~13 SP)

**Goal:** Generator.tsx decomposed into sub-components; search_queries router has a service layer; content script is modular. These are pure refactors — no behavior changes.

**Definition of Done:**
- [ ] Generator.tsx < 400 lines; sub-components in `sidebar/components/`
- [ ] search_lab.py service layer extracted; router is thin HTTP adapter
- [ ] content/index.ts < 400 lines; scorers and scrapers in sub-modules
- [ ] All TypeScript type checks pass
- [ ] Extension build output identical to pre-refactor

**Items:**

| ID | Title | SP | Type | Files |
|----|-------|----|------|-------|
| TD-018 | Decompose Generator.tsx | 5 | Architecture | `pages/Generator.tsx` → `components/CoverLetterPanel.tsx`, `AnalysisPanel.tsx`, `ScreeningPanel.tsx`, `JobHeader.tsx` |
| TD-028 | Extract search_lab service layer | 3 | Architecture | `search_queries.py:523–932` → `services/search_lab.py` |
| TD-027 | Decompose content/index.ts | 5 | Architecture | `content/index.ts` → `content/scoring.ts`, `content/scrapers/proposals.ts`, `content/scrapers/contracts.ts`, `content/scrapers/saved.ts` |

**Sprint 3 notes:** Sprint 3 is purely quality-of-life and maintainability. All behavior stays identical. Can be done incrementally (Generator.tsx first since it affects UI development velocity the most). TD-027 is the largest single item in the backlog.

---

## Backlog (Deferred)

| ID | SP | Title | Why Deferred |
|----|-----|-------|-------------|
| DIST-01 | 2 | Chrome Web Store submission | v1.0.0 milestone, not now |
| DOC-01 | 1 | User onboarding docs | Beta use only |
| EXT-03 | 1 | DOM selector health monitoring | Low priority |
| DATA-01 | 2 | Geo tier config in profile | Hardcoded works fine |
| DATA-02 | 1 | Milestone row 3 selector verification | Low-frequency feature |
| EXT-02 | 2 | was_hired backfill | Operational (re-run import) |

---

## Completion Forecast

| Sprint | SP | Cumulative | State After |
|--------|-----|-----------|-------------|
| Sprint 1 | 9 | 9 | Secure, tested, no blank crashes |
| Sprint 2 | 8 | 17 | Feature-complete (saved jobs badges), clean builds |
| Sprint 3 | 13 | 30 | Maintainable, decomposed codebase |
| **v1.0.0** | **+5 backlog** | **35** | **CWS submission ready** |

---

## Key Dependencies & Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Upwork DOM changes for `article[data-test="JobTile"]` | Breaks saved jobs scoring | Fallback selector chain (same as notification scoring) |
| Anthropic API rate limits on profile optimize | Already mitigated by 24h cache | Sprint 1 rate limit adds server-side throttle |
| Generator.tsx decomposition regression | Any cover letter flow breakage | Type-check + manual end-to-end test before commit |

---

*Generated: 2026-03-18. Successor to: [prior TODO](../2026-02-18/TODO_2026-02-18.md). Sprint 1 starts immediately.*
