# Plan: Scored Jobs View — Filter, Rate, and Self-Improve

**Author:** Chris Therriault
**Date:** 2026-03-08
**Status:** Ready to implement
**Priority:** High — closes the feedback loop between scoring and learning

---

## Problem Statement

When the notification scorer or saved-jobs scorer runs, scores disappear when the user leaves the page. There is no way to:
- Browse previously scored jobs with their scores and chips
- Filter by skill type (SQL, AI, Long-term, etc.) or pay range
- Navigate back to an interesting job
- Record why a job is a good or bad match
- Give a human 1–5 star rating that corrects or reinforces the AI score
- Feed those ratings back into the scoring rubric for continuous improvement

---

## Goals

1. **Scored Jobs view** in the sidebar — persistent list of every job scored this session and historically
2. **Chip + pay filters** — narrow by skill type and budget range
3. **Click-to-navigate** — open any job in the Upwork tab
4. **User rating** (1–5 stars, single click) + optional comment — human rubric correction
5. **Self-improvement loop** — 4–5 star rated jobs feed into `find_similar_wins`-style calibration in the scoring LLM prompt

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage for scored jobs | API DB + local cache | Local for instant display; DB for persistence across devices and for the self-improvement loop |
| Storage for ratings | API DB only | Ratings must reach the LLM calibration; local-only would silo them |
| JobReview vs. extending Application | Separate `job_reviews` table | Applications track submissions; reviews track evaluation intent. Some scored jobs are never applied to. |
| Rating jobs not yet in DB | Upsert by URL | The review endpoint accepts `upwork_job_url` and creates a minimal Job record if none exists |
| When to write to DB | On scoring completion (background) | The background already calls `/api/v1/jobs/analyze`; we add a lightweight parallel write to `/api/v1/job-reviews/record-scored` |

---

## Component Map

```
chrome.storage.local                 API DB
  scoredJobsCache                      job_reviews table
  { url → ScoredJobEntry }             { id, user_id, upwork_job_url,
                                          ai_score, chips, user_rating,
                                          user_comment, job_title,
                                          scored_at, created_at }
         │                                      │
         │  read on open                        │ write on score + rating
         ▼                                      ▼
  ScoredJobs.tsx (sidebar page)     GET /api/v1/job-reviews
  - filters, list, rating UI        POST /api/v1/job-reviews
                                    PATCH /api/v1/job-reviews/{id}
                                            │
                                            ▼
                               job_analysis.py
                               find_similar_highly_rated()
                               → blended into LLM scoring prompt
```

---

## Sprint A: Database + API

### A1. Migration `011_add_job_reviews.py`

```python
op.create_table(
    'job_reviews',
    sa.Column('id', sa.String(36), primary_key=True),
    sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
    sa.Column('upwork_job_url', sa.String(500), nullable=False),
    sa.Column('upwork_job_id', sa.String(100), nullable=True),
    sa.Column('job_title', sa.String(500), nullable=False),
    sa.Column('ai_score', sa.Float(), nullable=True),        # score UpApply gave
    sa.Column('chips', sa.JSON(), nullable=True),            # ['AI', 'Long-term', '$150/hr']
    sa.Column('budget_amount', sa.String(100), nullable=True),
    sa.Column('budget_type', sa.String(20), nullable=True),  # hourly | fixed
    sa.Column('user_rating', sa.Integer(), nullable=True),   # 1–5
    sa.Column('user_comment', sa.Text(), nullable=True),
    sa.Column('scored_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    sa.UniqueConstraint('user_id', 'upwork_job_url', name='uq_job_review_user_url'),
)
```

### A2. Model `api/app/models/job_review.py`

Fields mirror the migration. Include `embedding: Vector` so highly-rated jobs can be queried semantically.

```python
class JobReview(Base):
    __tablename__ = "job_reviews"
    # ... all columns above
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(1536), nullable=True)
```

### A3. Schemas `api/app/schemas/job_review.py`

```python
class JobReviewUpsert(BaseModel):
    upwork_job_url: str
    upwork_job_id: Optional[str] = None
    job_title: str
    ai_score: Optional[float] = None
    chips: Optional[List[str]] = None
    budget_amount: Optional[str] = None
    budget_type: Optional[str] = None
    scored_at: Optional[datetime] = None

class JobReviewRate(BaseModel):
    user_rating: int        # 1–5
    user_comment: Optional[str] = None

class JobReviewResponse(BaseModel):
    id: str
    upwork_job_url: str
    job_title: str
    ai_score: Optional[float]
    chips: Optional[List[str]]
    budget_amount: Optional[str]
    budget_type: Optional[str]
    user_rating: Optional[int]
    user_comment: Optional[str]
    scored_at: Optional[datetime]
    created_at: datetime
    model_config = {"from_attributes": True}

class JobReviewListResponse(BaseModel):
    reviews: List[JobReviewResponse]
    total: int
```

### A4. Router `api/app/api/v1/job_reviews.py`

```
POST   /api/v1/job-reviews              Upsert by URL (called on score completion)
PATCH  /api/v1/job-reviews/{id}/rate    Set user_rating + user_comment
GET    /api/v1/job-reviews              List with filters:
                                          ?min_score=70
                                          ?max_score=100
                                          ?chip=AI&chip=SQL     (multi)
                                          ?min_budget=50
                                          ?max_budget=200
                                          ?has_rating=true
                                          ?sort=score|recent|rating
                                          ?limit=50&offset=0
DELETE /api/v1/job-reviews/{id}         Remove from view
```

The `GET` endpoint returns denormalised data suitable for the sidebar list — no join needed.

### A5. Wire self-improvement in `api/app/services/job_analysis.py`

Add `find_similar_highly_rated(db, user_id, query_embedding, limit=3)`:

```python
sql = text("""
    SELECT job_title, user_comment, ai_score, chips,
           1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
    FROM job_reviews
    WHERE user_id = :user_id
      AND user_rating >= 4
      AND embedding IS NOT NULL
    ORDER BY embedding <=> CAST(:embedding AS vector)
    LIMIT :limit
""")
```

Modify `score_job_with_llm` prompt to include up to 3 highly-rated reviews as positive calibration examples, alongside the existing hired-contract examples. User comments provide richer signal than job titles alone.

Register the router in `api/app/main.py`.

---

## Sprint B: Local Cache + Background Writer

### B1. Extend `_applyBadgeResult` in `extension/src/content/index.ts`

After updating the badge, also write to `scoredJobsCache` in `chrome.storage.local`:

```typescript
// Merge into scoredJobsCache
chrome.storage.local.get('scoredJobsCache', (data) => {
  const cache: Record<string, ScoredJobCacheEntry> = data.scoredJobsCache || {};
  cache[jobUrl] = {
    url: jobUrl,
    title: item.title,
    score,
    chips,
    scored_at: new Date().toISOString(),
    // preserve any existing user_rating / user_comment
    user_rating: cache[jobUrl]?.user_rating,
    user_comment: cache[jobUrl]?.user_comment,
  };
  chrome.storage.local.set({ scoredJobsCache: cache });
});
```

Type: `ScoredJobCacheEntry` — add to `extension/src/types/index.ts`.

### B2. Background: write to API on score completion

In the `SCORE_JOB_WITH_DATA` handler (or after `_applyBadgeResult` fires via a new message `RECORD_SCORED_JOB`):

```typescript
// Fire-and-forget — don't block badge display
fetch(`${apiBase}/api/v1/job-reviews`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
  body: JSON.stringify({ upwork_job_url: jobUrl, job_title: title, ai_score: score, chips, scored_at }),
  signal: AbortSignal.timeout(10_000),
}).catch(() => {}); // silent — scoring display should never depend on this write
```

Since `_scoreOneNotif` now fetches directly from the content script (no SW), send a `RECORD_SCORED_JOB` message to the background after scoring completes, letting the SW do the DB write with the auth token.

---

## Sprint C: Sidebar UI — `ScoredJobs.tsx`

### C1. New sidebar page

File: `extension/src/sidebar/pages/ScoredJobs.tsx`

**Data flow:**
1. On mount: read `scoredJobsCache` from `chrome.storage.local` → local state
2. Merge with `GET /api/v1/job-reviews` (for persisted ratings from previous sessions)
3. Combine: local cache wins for freshness, API wins for user_rating/user_comment

### C2. Filter bar

```
[Score ≥ ___] [Chips: ▼ SQL AI Long-term CTO …] [Pay $___–$___] [Sort ▼]
```

- **Score filter**: input or preset buttons (All / ≥50 / ≥70 / ≥90)
- **Chip filter**: multi-select from all unique chips in the list; each chip is a toggle pill
- **Pay filter**: parse dollar values out of budget chips (e.g. `$150/hr`, `$500`) → min/max sliders
- **Sort**: Score (default) | Most Recent | User Rating

### C3. Job card

```
┌─────────────────────────────────────────────────────────┐
│  [87]  React Developer for SaaS Dashboard               │ ← score badge + title (clickable)
│        AI  React  Long-term  $85/hr                     │ ← chips
│  ★★★★☆  [Add comment...]                               │ ← 1-5 stars + comment
└─────────────────────────────────────────────────────────┘
```

- Title click: sends `NAVIGATE_TO_JOB` → `chrome.tabs.update({ url: jobUrl })`
- Star click: instant local state update + debounced `PATCH /api/v1/job-reviews/{id}/rate`
- Comment: textarea expands on focus, saves on blur

### C4. Score badge colours (match notification badges)

| Score | Background | Text |
|-------|-----------|------|
| ≥90 | `#15803d` (deep green) | white |
| ≥80 | `#22c55e` (light green) | dark green |
| ≥70 | `#ca8a04` (amber) | white |
| <70 | `#dc2626` (red) | white |

### C5. Empty state

When no scored jobs: "Score some jobs first — click the score button on the notifications bell or saved jobs page."

---

## Sprint D: Navigation wiring

### D1. Add `ScoredJobs` to sidebar navigation

File: `extension/src/sidebar/App.tsx` (or equivalent nav)
- Add tab/icon for "Scored Jobs" view (use a star or list icon)
- Route: `'scored'` view type

### D2. Background: `NAVIGATE_TO_JOB`

```typescript
case 'NAVIGATE_TO_JOB':
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]?.id) {
      chrome.tabs.update(tabs[0].id, { url: message.url });
    }
  });
  sendResponse({ success: true });
  return false;
```

---

## Sprint E: Self-improvement integration

### E1. Modify scoring prompt

In `score_job_with_llm` (after the existing `similar_wins` examples), add:

```python
if highly_rated:
    prompt_parts.append("Jobs this user rated 4-5 stars (strong matches by their judgment):")
    for r in highly_rated:
        prompt_parts.append(f"- {r['job_title']} (their note: {r.get('user_comment', 'strong fit')})")
    prompt_parts.append("")
```

### E2. Negative signal (1–2 star jobs)

Query `job_reviews WHERE user_rating <= 2` and add to the prompt as jobs to score lower:

```python
if low_rated:
    prompt_parts.append("Jobs this user rated 1-2 stars (poor matches by their judgment):")
    for r in low_rated:
        prompt_parts.append(f"- {r['job_title']} (their note: {r.get('user_comment', 'not a good fit')})")
```

### E3. Embedding generation for reviews

When `user_rating` is set (or on upsert), generate an embedding from `f"{job_title}\n{user_comment or ''}"` and store in `job_reviews.embedding`. This enables semantic similarity search in `find_similar_highly_rated`.

---

## Files to Create / Modify

### New files
| File | Purpose |
|------|---------|
| `api/alembic/versions/011_add_job_reviews.py` | Migration |
| `api/app/models/job_review.py` | SQLAlchemy model |
| `api/app/schemas/job_review.py` | Pydantic schemas |
| `api/app/api/v1/job_reviews.py` | FastAPI router |
| `extension/src/sidebar/pages/ScoredJobs.tsx` | New sidebar page |

### Modified files
| File | Change |
|------|--------|
| `api/app/main.py` | Register `job_reviews` router |
| `api/app/models/__init__.py` | Import `JobReview` |
| `api/app/services/job_analysis.py` | Add `find_similar_highly_rated`, update `score_job_with_llm` |
| `extension/src/types/index.ts` | Add `ScoredJobCacheEntry` |
| `extension/src/content/index.ts` | Write to `scoredJobsCache` in `_applyBadgeResult` |
| `extension/src/background/index.ts` | Add `RECORD_SCORED_JOB` + `NAVIGATE_TO_JOB` handlers |
| `extension/src/lib/api-client.ts` | Add `JobReview` interface + CRUD methods |
| `extension/src/sidebar/App.tsx` | Add "Scored Jobs" nav tab |

---

## Execution Order

1. **Sprint A** — Migration + model + schema + router + self-improvement
   - `alembic upgrade head` on Render after deploy
2. **Sprint B** — Local cache write in content script + background `RECORD_SCORED_JOB`
3. **Sprint C** — `ScoredJobs.tsx` page (read-only first, then add rating UI)
4. **Sprint D** — Nav wiring + `NAVIGATE_TO_JOB`
5. **Sprint E** — Wire highly-rated / low-rated into LLM scoring prompt

---

## Verification

1. Score notifications → open "Scored Jobs" tab → list appears with scores and chips
2. Chip filter: toggle "AI" → only AI-tagged jobs shown
3. Score filter: ≥70 → red jobs disappear
4. Pay filter: $100–$200/hr → only hourly jobs in range shown
5. Click job title → Upwork tab navigates to that job
6. Click 4 stars → star fills instantly, rating saved; `GET /api/v1/job-reviews` shows `user_rating: 4`
7. Type a comment, blur → saved; next session shows comment
8. Score a new job semantically similar to a 5-star rated job → score is higher than baseline
9. Score a new job semantically similar to a 1-star rated job → score is lower than baseline

---

## Open Questions

- **Deduplication across sessions**: `scoredJobsCache` grows unbounded. Cap at 500 entries (evict oldest by `scored_at`) or add a "Clear old" button.
- **Pagination**: API returns up to 200 reviews; sidebar list should virtual-scroll or paginate.
- **Chip colour consistency**: Use the same `_CHIP_COLORS` map from the content script to colour chips in the sidebar list — avoids visual inconsistency.
- **Rating without navigating to sidebar**: Consider a "Rate this job" micro-UI injected into the Upwork page next to the score badge (future sprint).
