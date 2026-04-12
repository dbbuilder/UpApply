# Feature Completeness — 2026-04-12

## Backend Endpoints vs Extension UI

| Backend Endpoint | Extension UI | Status |
|-----------------|--------------|--------|
| POST /auth/register | Auth.tsx | COVERED |
| POST /auth/login | Auth.tsx | COVERED |
| GET /auth/me | MePage.tsx | COVERED |
| GET/PUT /profile | EditProfile.tsx + ProfileWizard | COVERED |
| PUT /profile/goals | EditProfile.tsx + StepGoals | COVERED |
| PUT /profile/preferences | EditProfile.tsx + StepPreferences | COVERED |
| PUT /profile/dealbreakers | EditProfile.tsx + StepDealbreakers | COVERED |
| PUT /profile/pricing | EditProfile.tsx + StepPricing | COVERED |
| POST /profile/import-resume | StepIdentity.tsx | COVERED |
| POST /profile/optimize | OptimizePage.tsx | COVERED |
| POST /memories | Memories.tsx | COVERED |
| GET /memories | Memories.tsx + StepMemories | COVERED |
| POST /memories/search | Memories.tsx | COVERED |
| POST /memories/bulk-import | StepMemories.tsx | COVERED |
| POST /jobs/analyze | background/index.ts (SCORE_JOB_WITH_DATA) | COVERED |
| POST /jobs | store.ts | COVERED |
| GET /jobs | QueuePage.tsx, History.tsx | COVERED |
| GET /jobs/{id}/match | store.ts | COVERED |
| POST /jobs/cover-letters/generate | store.ts | COVERED |
| GET /jobs/cover-letters | QueuePage.tsx | COVERED |
| POST /cover-letters/{id}/regenerate | store.ts | COVERED |
| PUT /cover-letters/{id}/submit | store.ts | COVERED |
| POST /cover-letters/{id}/improve | store.ts (via improveLetterRequest) | COVERED |
| POST /applications | store.ts | COVERED |
| GET /applications | QueuePage.tsx | COVERED |
| GET /applications/stats | Analytics.tsx | COVERED |
| PUT /applications/{id}/outcome | store.ts | COVERED |
| DELETE /applications/{id} | QueuePage.tsx | COVERED |
| POST /feedback | BetaFeedback.tsx | COVERED |
| GET /feedback/analytics/dashboard | InsightsPage.tsx | COVERED |
| GET /search-queries | History.tsx | COVERED |
| POST /search-queries | History.tsx | COVERED |
| DELETE /search-queries/{id} | History.tsx | COVERED |
| POST /search-queries/generate | History.tsx | COVERED |
| POST /search-queries/evaluate | History.tsx | COVERED |
| POST /search-queries/optimize | History.tsx | COVERED |
| GET /job-reviews | FindPage.tsx | COVERED |
| PATCH /job-reviews/{id}/rate | FindPage.tsx | COVERED |
| POST /work-logs | WorkTab.tsx | COVERED |
| GET /work-logs | WorkTab.tsx | COVERED |
| PATCH /work-logs/{id} | WorkTab.tsx | COVERED |
| DELETE /work-logs/{id} | WorkTab.tsx | COVERED |
| POST /work-logs/extract-image | WorkTab.tsx + AttachmentPicker | COVERED |
| POST /jobs/suggest-milestones | Generator.tsx (MilestonePanel) | COVERED |
| POST /jobs/import-contracts | background/index.ts | COVERED |
| POST /jobs/import-bulk | History.tsx | COVERED |
| POST /import-chatgpt-conversations | ImportPage.tsx | COVERED |

## Gaps

**None identified.** All backend endpoints have corresponding extension UI coverage.

## Notes

- `/api/v1/jobs/active-contracts` — used in background/index.ts for contracts page detection
- `/api/v1/applications/backfill-proposals` — internal admin endpoint, no UI needed
- `/api/v1/search-queries/seed` and `/bulk-import` — used internally in History.tsx auto-seed logic
