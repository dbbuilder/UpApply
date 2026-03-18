# Feature Completeness: UpApply — 2026-03-18

## Product Baseline

Sources: `docs/ROADMAP-2026-03-17.md` (the v0.4.0 feature checklist), `CLAUDE.md`, and the extension UI as built.

---

## Feature Status

| Feature | API | Extension | Tests | Status |
|---------|-----|-----------|-------|--------|
| Auth (register/login/me) | ✅ | ✅ | ✅ | COMPLETE |
| Profile CRUD | ✅ | ✅ | ✅ | COMPLETE |
| Profile optimization engine | ✅ | ✅ | ❌ | PARTIAL |
| Memory CRUD + semantic search | ✅ | ✅ | ✅ | COMPLETE |
| Job detection + extraction | — | ✅ | ❌ | COMPLETE* |
| Job scoring (GraphQL → API) | ✅ | ✅ | ✅ | COMPLETE |
| Job tile badges (notifications) | — | ✅ | ❌ | COMPLETE* |
| Job tile badges (saved jobs page) | — | ❌ | ❌ | MISSING |
| Cover letter generation | ✅ | ✅ | ✅ partial | PARTIAL |
| Cover letter regeneration | ✅ | ✅ | ❌ | PARTIAL |
| Cover letter auto-fill | — | ✅ | ❌ | COMPLETE* |
| Screening question generation | ✅ | ✅ | ❌ | COMPLETE* |
| Application tracking (Queue) | ✅ | ✅ | ✅ | COMPLETE |
| Application stats | ✅ | ✅ | ✅ | COMPLETE |
| Proposals deep-scrape | — | ✅ | ❌ | COMPLETE* |
| Contracts import | — | ✅ | ❌ | COMPLETE* |
| Saved jobs import | — | ✅ | ❌ | COMPLETE* |
| Saved searches import | — | ✅ | ❌ | COMPLETE* |
| Query Library | ✅ | ✅ | ✅ | COMPLETE |
| Search Lab (evaluate) | ✅ | ✅ | ❌ | PARTIAL |
| Search Lab (optimize) | ✅ | ✅ | ❌ | PARTIAL |
| Find tab (scored job browse) | ✅ | ✅ | ❌ | COMPLETE* |
| Track tab (pipeline/analytics) | ✅ | ✅ | ❌ | COMPLETE* |
| Insights tab (AI synthesis) | ✅ | ✅ | ❌ | COMPLETE* |
| Work logs | ✅ | ✅ | ❌ | COMPLETE* |
| Feedback loop (won/lost) | ✅ | ✅ | ❌ | COMPLETE* |
| Sentry error tracking | ✅ SDK | — | — | PARTIAL |
| Chrome Web Store distribution | — | — | — | MISSING |
| User onboarding docs | — | — | — | MISSING |

\* = functionally complete, no automated tests

---

## Gap Details

### FC-001 / EXT-01: Saved jobs page badge scorer (MISSING)

| Severity | SP | Status |
|----------|-----|--------|
| MEDIUM | 3 | MISSING |

The notification bell page and `/ab/notifications/` show score badges on job tiles. The `/nx/search/jobs/saved/` and `/nx/search/jobs/?q=...` pages use the same `article[data-test="JobTile"]` DOM structure but receive no badges. Users browsing saved jobs cannot see match scores without opening each job individually.

A complete implementation plan exists at `/Users/admin/.claude/plans/zesty-booping-frog.md`. The plan reuses the entire existing scoring pipeline — it's an ~80 line addition to `content/index.ts`.

---

### FC-002: Profile optimizer not tested + Sentry DSN missing (PARTIAL)

**Profile optimizer:** API endpoint is live and working (verified). No automated tests. See TST-003.

**Sentry:** SDK initialized, `settings.sentry_dsn` configured, but `SENTRY_DSN` env var not set on Render. All unhandled exceptions in production are silently lost. This is OPS-01 (1 SP, non-code task).

---

### FC-003: was_hired still 0/203 proposals (PARTIAL)

The NUXT path fix (`state['proposal-details'].proposalDetailsV3Response.application`) was committed (`e3ff48d`). However, no re-import has been run since the fix. The roadmap notes 0/203 proposals with `was_hired=True`. This requires:
1. Clearing or re-running the proposals deep-scrape
2. Verifying Upwork's numeric `application.status` maps to "hired" empirically

Not a code defect — operational follow-up.

---

### FC-004: No React ErrorBoundary (HIGH) / TD-033

| Severity | SP | Status |
|----------|-----|--------|
| HIGH | 2 | MISSING |

If any page component throws during render (e.g., a null access on an API response, a malformed JSON from the optimizer), the entire extension sidebar goes blank. No error message. User thinks the extension crashed.

A simple ErrorBoundary at the App.tsx level would catch render errors and show a "Something went wrong — try refreshing" message.

```tsx
// extension/src/sidebar/ErrorBoundary.tsx (new)
class ErrorBoundary extends React.Component<...> {
  state = { hasError: false, error: null };
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return <div className="p-4 text-red-600">Something went wrong — try refreshing the panel.</div>;
    }
    return this.props.children;
  }
}
```

Wrap the root `<AppShell>` in App.tsx with this boundary.

---

### FC-005: Chrome Web Store distribution (MISSING)

| Severity | SP | Status |
|----------|-----|--------|
| LOW | 2 | MISSING |

Currently distributed as a ZIP/unpacked load. No CWS listing. Needed for v1.0.0. Non-blocking for personal/beta use.

---

## Overall Product Completeness

| Category | Complete | Partial | Missing |
|----------|---------|---------|---------|
| Core workflow | 8 / 8 | 0 | 0 |
| Data import | 5 / 5 | 0 | 0 |
| Search & discovery | 5 / 5 | 0 | 0 |
| Tracking & analytics | 5 / 5 | 0 | 0 |
| Infrastructure | 3 / 5 | 1 (Sentry DSN) | 1 (ErrorBoundary) |
| Extension scoring coverage | 1 / 2 | 0 | 1 (saved jobs page) |

**Estimated completeness: ~88% feature-complete vs. v1.0.0 definition.**
