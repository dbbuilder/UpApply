# Tech Debt Remediation — 2026-04-12

## Actions Taken This Review

### TD-034 — Migrate console.log → logger in draft-saver.ts (DONE, 0.5 SP)

**File:** `/Users/admin/dev2/UpApply/extension/src/content/draft-saver.ts`

**Changes:**
- Added `import { logger } from '../lib/logger';`
- Replaced 8 `console.log(...)` calls with `logger.log(...)`:
  - Line ~141: "Draft saved"
  - Line ~180: "Draft cleared"
  - Line ~289: "Restored cover letter draft"
  - Line ~299: "Restored bid amount draft"
  - Line ~317: "Restored screening answer for:"
  - Line ~385: "Draft save listeners attached"
  - Line ~519: "Draft saver initializing on apply page"
  - Line ~563: "Draft saver timed out waiting for form"

**Why:** `logger.log` is gated by `import.meta.env.DEV`, so production builds emit no console noise. The `logger.error` path always emits — that's correct behavior retained throughout.

**Verification:** `npm run type-check` passes clean after changes.

---

## Remaining console.log Analysis

All remaining `console.error(...)` calls in the extension are **correct to keep** — they are:
- In `catch` blocks where they are the only error signal to the developer
- In background service worker error paths (no Sentry in content scripts)
- The logger.error function itself (`lib/logger.ts:6`) which always emits

No action needed on `console.error` calls.

---

## Python print() Statements

No bare `print()` found in `api/app/**`. Clean.

---

## TODO/FIXME Markers

No `TODO`, `FIXME`, `HACK`, `XXX`, or `NOCOMMIT` markers found in source files (excluding comment lines about URL patterns).
