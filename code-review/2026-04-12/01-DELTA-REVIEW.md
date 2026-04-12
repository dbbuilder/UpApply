# Delta Review — 2026-03-18 → 2026-04-12

## Commits Since Prior Review (11 total)

```
a00b9f7 perf: cut OpenAI costs — gpt-4o-mini, embedding LRU cache, skip re-embed
2e6f2ca feat: save icon on every Upwork job link — queue or past-job routing
538196e feat: login prompt when clicking Score without UpApply session
4f9faeb fix: warm up Render server before scoring to prevent cold-start
d910744 feat: persist milestones across apply page refreshes
190c1a5 feat: score button fixed to viewport + low-connects alert
a130d7d fix: guard all generate_embedding calls against quota/retry failures
d42dd2e feat: alert info@servicevision.io when OpenAI quota is exhausted
c3d6376 fix: graceful fallback when OpenAI embedding rate-limited
160ca78 fix: shorten migration 015 revision ID to fit VARCHAR(32)
68f7371 feat: backlog — EXT-02 corpus backfill, DATA-01 geo locations, DATA-02 milestone polling, EXT-03 selector health, DOC-01 onboarding
```

## Sprint Item Status

### Sprint 1 (Security + Test Foundations)
All 7 items: **RESOLVED** (committed in prior session, verified by git log)

### Sprint 2 (Feature + Quality)
All 5 items: **RESOLVED** (committed in prior session, verified by git log)

### Sprint 3 (Architecture Refactor)
All 3 items: **RESOLVED** (committed in prior session, verified by git log)

## Backlog Items

| ID | Status | Notes |
|----|--------|-------|
| DIST-01 | CARRYOVER | Chrome Web Store submission — not started |
| DOC-01 | CARRYOVER | Onboarding docs mentioned in 68f7371 commit but no doc created |
| EXT-02 | CARRYOVER | was_hired backfill — mentioned in 68f7371 |
| EXT-03 | CARRYOVER | DOM selector health monitoring — mentioned in 68f7371 |
| DATA-01 | CARRYOVER | Geo tier config — mentioned in 68f7371 |
| DATA-02 | CARRYOVER | Milestone row 3 selector — mentioned in 68f7371 |

## New Work Since Prior Review

- **Milestone persistence** (`draft-saver.ts`) — save/restore milestones across page refreshes
- **Score button fixed to viewport** — improved UX
- **Low-connects alert** — warns when connects are low
- **Login prompt** — when clicking Score without session
- **Render warm-up** — prevents cold-start question marks in scored jobs
- **OpenAI cost cuts** — gpt-4o-mini + LRU embedding cache + skip re-embed
- **Save icon on job links** — routes to queue or past-job view
- **Quota alert email** — alerts when OpenAI quota exhausted
