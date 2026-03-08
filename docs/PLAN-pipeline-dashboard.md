# Plan: Pipeline Dashboard — Full Job Application Flow Visibility

**Author:** Chris Therriault
**Date:** 2026-03-08
**Status:** Ready to implement
**Priority:** High — current "Stats" page shows only 4 aggregate numbers with no pipeline, history, or trends

---

## Problem Statement

The current Analytics page (`Analytics.tsx`) shows:
- 4 summary numbers (total proposals, response rate, hire rate, hired count)
- Proposal breakdown (submitted / responded / hired)

It does **not** show:
- The live pipeline — where are jobs right now in the funnel?
- History — a timeline of what was applied to and what happened
- Trends — is performance improving or declining over time?
- AI score calibration — did high-score jobs actually convert better?
- Skill performance — which skill categories win more often?
- Earnings trajectory — dollars won by month
- Time-to-response patterns — how long do clients take?

The existing `GET /api/v1/feedback/analytics/dashboard` endpoint already computes `weekly_applications`, `top_skills`, `avg_match_score`, `insights` — but the sidebar never calls it.

---

## Dashboard Structure (3 sections / tabs)

### Tab 1: Pipeline (live funnel)
### Tab 2: History (timeline)
### Tab 3: Trends (over time)

---

## Tab 1 — Pipeline (Funnel View)

Visual funnel showing jobs at each stage:

```
  Scored          ████████████████████████  142  (from job_reviews)
  Applied         ████████████████          87   (proposals submitted)
  Viewed          ████████                  41   (client_responded or viewed)
  Responded       █████                     23   (client replied)
  Interviewed     ██                        9
  Hired           █                         4
                                           ──────────
  Conversion:  Applied→Hired  4.6%    Score→Applied  61%
```

Each bar is clickable → shows the actual jobs at that stage (title + date + score + chip tags).

**Data sources:**
- Scored: `GET /api/v1/job-reviews?has_rating=false` count (jobs scored but not necessarily applied)
- Applied+: `GET /api/v1/proposals/stats` (existing)
- Weekly trend sparkline for each stage

**New API fields needed on `/api/v1/proposals/stats`:**
```json
{
  "total_proposals": 87,
  "submitted": 23,
  "viewed": 41,
  "responded": 23,
  "interviewed": 9,
  "hired": 4,
  "hire_rate": 4.6,
  "response_rate": 26.4,
  "interview_rate": 10.3,
  "total_earnings": 14250.00,
  "avg_match_score_applied": 71.2,
  "avg_match_score_hired": 84.5,
  "avg_days_to_response": 3.8,
  "scored_not_applied": 55
}
```

Currently missing from `proposals/stats`: `interviewed`, `avg_match_score_applied`, `avg_match_score_hired`, `avg_days_to_response`, `scored_not_applied`.

**Application status enum** already has `interviewed` — just not counted. Add to the SQL.

---

## Tab 2 — History (Timeline)

A reverse-chronological list of ALL applications, showing the full journey of each:

```
┌─ Mar 6  AI Dashboard for ServiceVision · Score: 88  ★★★★☆
│         Submitted → Client Viewed → Responded → Hired ✓  $3,200
│         Budget: $3,000–$4,000  Skills: AI, Python, SaaS
│         Cover letter: [preview snippet...]
│
├─ Mar 3  React SaaS MVP · Score: 74  ★★★☆☆
│         Submitted → (no response after 8 days)
│         Budget: Fixed $500  Skills: React, API
│
└─ Feb 28 Fractional CTO · Score: 91  ★★★★★
          Submitted → Client Viewed → Responded
          Budget: $150/hr  Skills: CTO, Long-term
```

**Features:**
- Filter by status (All / Active / Hired / No Response / Archived)
- Filter by date range (last 7 days / 30 days / 90 days / all time)
- Search by title or skill
- Click to expand: see cover letter, Q&A answers, client notes
- Outcome tagging: "Client ghosted", "Rate too high", "Skills mismatch", "Hired" — user adds tag

**Data source:**
- `GET /api/v1/proposals?limit=200&sort=submitted_at_desc` — existing endpoint (needs `sort` param)
- Join with `job_reviews` for AI score (score not currently stored on proposals)
- Join with `applications` for status progression and earnings

**Gap:** The `Proposal` model has `was_hired`, `client_responded`, `status` but does NOT store the job's AI match score. Need to either:
1. Add `ai_score` field to `Proposal` (set at import time from `job_reviews`) — preferred
2. Or join through `jobs.match_score` via `proposals.job_id`

---

## Tab 3 — Trends (Over Time)

### 3a. Weekly application volume + outcomes
Bar chart: submissions per week, coloured by outcome (hired=green, responded=blue, no response=gray)

```
Week of Feb 17  ████ 4  (1 responded)
Week of Feb 24  ████████ 8  (2 responded, 1 hired)
Week of Mar 3   ██████ 6  (1 hired)
```

### 3b. Score calibration
Line chart: avg AI match score for hired vs not-hired proposals over time. Goal: converging lines = AI getting better; diverging = rubric drift.

```
Score 90 ┤     hired ····●·····●
      80 ┤    ·····●···/
      70 ┤   not hired ──────────
      60 ┤
         └─────────────────────▶ time
```

### 3c. Earnings by month
Bar chart: `SUM(earnings)` per calendar month.

### 3d. Skill win rates
Table: top 10 skills by proposal count + their hire rate

```
Skill      Proposals  Responses  Hired  Rate
AI            24          8        3    12.5%
Python        18          6        2    11.1%
React         15          3        1     6.7%
CTO            5          3        2    40.0%
```

### 3e. Time-to-response distribution
Histogram: how many days until client responded (or didn't). Helps calibrate when to move on.

**Data source:** `GET /api/v1/feedback/analytics/dashboard` already returns:
- `weekly_applications: [{week, applications, responses}]` ✓
- `top_skills: [{skill, success_rate, applications}]` ✓
- `avg_match_score` (single number, not by outcome) — needs extension

---

## API Changes Required

### A1. Extend `GET /api/v1/proposals/stats`

Add to the SQL in `proposals.py`:
```sql
COUNT(*) FILTER (WHERE status = 'interviewed') as interviewed,
AVG(j.match_score) FILTER (WHERE p.was_hired = true) as avg_score_hired,
AVG(j.match_score) as avg_score_applied,
AVG(EXTRACT(EPOCH FROM (p.updated_at - p.submitted_at))/86400)
  FILTER (WHERE p.client_responded = true) as avg_days_to_response
FROM proposals p
LEFT JOIN jobs j ON j.id = p.job_id
WHERE p.user_id = :user_id
```

### A2. Extend `GET /api/v1/feedback/analytics/dashboard`

Add:
- `score_by_outcome: {hired: float, responded: float, no_response: float}` — calibration view
- `earnings_by_month: [{month: string, earnings: float}]` — monthly revenue
- `skill_win_rates: [{skill, proposals, responses, hired, hire_rate}]` — expanded from `top_skills`
- `time_to_response_days: [{days_bucket: string, count: int}]` — distribution

### A3. Extend `GET /api/v1/proposals` (list endpoint)

Add query params:
- `sort=submitted_at_desc` (default) | `score_desc` | `status`
- `status=hired|submitted|responded|no_response`
- `since=2026-01-01` (date filter)
- `q=react` (title/skill search)

Return `ai_score` on each proposal (join from `jobs.match_score` or `job_reviews.ai_score`).

### A4. Proposals schema update

Add to `ProposalResponse`:
```python
ai_score: Optional[float] = None  # from job or job_review
```

---

## Extension UI Changes

### Replace `Analytics.tsx` with a 3-tab `Dashboard.tsx`

```tsx
<Dashboard>
  <Tab label="Pipeline">
    <FunnelChart data={stats} />
    <StageList stage="..." items={proposals} />
  </Tab>
  <Tab label="History">
    <FilterBar />
    <ProposalTimeline proposals={proposals} />
  </Tab>
  <Tab label="Trends">
    <WeeklyBarChart data={analytics.weekly_applications} />
    <ScoreCalibrationChart data={analytics.score_by_outcome} />
    <EarningsChart data={analytics.earnings_by_month} />
    <SkillWinRateTable data={analytics.skill_win_rates} />
  </Tab>
</Dashboard>
```

All charts are pure CSS/inline SVG — no chart library dependency (keeps bundle small for MV3).

### Pipeline Funnel — CSS implementation

Each stage is a `<div>` with width proportional to count. Color-coded:
- Scored: gray
- Applied: blue
- Viewed: blue-lighter
- Responded: amber
- Interviewed: orange
- Hired: green

Click a stage → expand an inline list of job titles with dates.

### History Timeline

Virtual list (show 20 at a time, load more button) to keep memory low in the sidebar.
Each item shows: date badge | score chip | title | status progress dots | outcome tag | earnings.

Outcome tag dropdown: `["Hired ✓", "Client ghosted", "Rate mismatch", "Skills mismatch", "Not interested", "Archived"]` — writes back to `proposals.status` via `PATCH /api/v1/proposals/{id}`.

### Trends Charts — pure CSS bars

Weekly bar chart: `<div style="height: ${(val/max)*60}px">` flex row.
Score calibration: two inline `<progress>` elements side by side.
Skill table: plain `<table>` with percentage bar `<div>`.

---

## Files to Create / Modify

### New files
| File | Purpose |
|------|---------|
| `extension/src/sidebar/pages/Dashboard.tsx` | Replaces Analytics.tsx; 3-tab layout |
| `extension/src/sidebar/components/FunnelChart.tsx` | CSS funnel |
| `extension/src/sidebar/components/WeeklyBarChart.tsx` | CSS bar chart |
| `extension/src/sidebar/components/ProposalTimeline.tsx` | History list |
| `extension/src/sidebar/components/SkillWinRateTable.tsx` | Skill table |

### Modified files
| File | Change |
|------|--------|
| `api/app/api/v1/proposals.py` | Extend `/stats`, extend list filters, add `ai_score` to response |
| `api/app/api/v1/feedback.py` | Extend `/analytics/dashboard` with new aggregates |
| `api/app/schemas/proposal.py` | Add `ai_score`, `interviewed` to response schemas |
| `extension/src/lib/api-client.ts` | Extend `ProposalStats`, `AnalyticsDashboard` interfaces; add list params |
| `extension/src/sidebar/App.tsx` | Route `'analytics'` → `Dashboard` |

---

## Execution Order

1. **API extensions** — extend `/stats` SQL, extend `/analytics/dashboard`, add list filters
2. **Schema + client updates** — `ProposalStats`, `AnalyticsDashboard`, `ProposalResponse.ai_score`
3. **Pipeline tab** — funnel chart + stage expand
4. **History tab** — timeline list + outcome tagging
5. **Trends tab** — charts from existing analytics data
6. **Nav rename** — "Stats" → "Pipeline" in sidebar nav

---

## Verification

1. Open Pipeline tab → funnel shows correct counts matching Upwork proposal page
2. Click "Hired (4)" → list expands with 4 hired job titles
3. Open History tab → most recent proposal at top; filter "Hired" → only hired show
4. Add outcome tag "Client ghosted" → proposal status updates; reloading shows same tag
5. Open Trends tab → weekly bars show submission volume; clicking a bar shows that week's jobs
6. Score calibration: if 5 hired proposals avg 84 score and 20 no-response avg 68 → shows those as distinct lines
7. Earnings chart: if earned $14,250 this quarter → bar visible for correct month
8. Skill win rates: CTO appears as highest hire rate if past data supports it

---

## Open Questions / Deferred

- **Real-time updates**: Pipeline tab doesn't auto-refresh when user scores more jobs in another tab. For now, add a manual "Refresh" button. Future: WebSocket or polling.
- **Multiple Upwork accounts**: Not in scope — single account assumed.
- **Export**: "Download CSV" for accountants — defer to later sprint.
- **Earnings currency**: Upwork pays in USD; assume all earnings are USD.
- **Interview status**: Upwork doesn't expose this directly — user tags it manually in the outcome dropdown or we infer it from proposal status string.
