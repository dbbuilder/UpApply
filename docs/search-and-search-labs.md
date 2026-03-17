# Search & Search Labs — Architecture and Workflow

**Project:** UpApply
**Date:** 2026-03-17
**Scope:** Query Library, search execution pipeline, and the Search Labs feedback loop

---

## Overview

The search system treats job discovery as a **learnable, optimizable process** — not a one-off search box. You maintain a persistent **Query Library** of saved searches, each accumulating performance statistics across runs. **Search Labs** is the feedback loop that continuously improves them: measuring coverage against your wins, grading live results, and using AI to suggest and optimize queries that aren't performing.

Your Upwork saved searches are the explicit starting point — the user's existing mental model of how clients look for people like them — and the system's job is to empirically test and iteratively improve on that baseline.

---

## System Layers

```mermaid
graph TB
    A["Upwork Saved Searches<br/>(your existing mental model)"] --> QL
    B["Profile-Seeded Queries<br/>(skills, title, domain extras)"] --> QL
    C["AI-Generated Queries<br/>(GPT from profile + past wins)"] --> QL

    QL["Query Library<br/>(persistent, with stats)"]

    QL --> RUN["Run Searches<br/>(single / batch stale)"]
    RUN --> JOBS["Scored Jobs<br/>(Find tab)"]
    RUN --> STATS["Update Query Stats<br/>(avg_score, high_score_count)"]

    QL --> LAB["Search Labs"]
    LAB --> EVAL["Coverage Evaluation<br/>(are we finding wins?)"]
    LAB --> OPT["Experiment → Grade → Optimize<br/>(are weak queries improvable?)"]

    EVAL --> NEW["New Gap-Covering Queries"]
    OPT --> VARIANTS["Broader / Narrower / Reframe Variants"]

    NEW --> QL
    VARIANTS --> QL
```

---

## Layer 1 — The Query Library

Every search is stored as a `SearchQuery` row with cumulative stats updated on each run.

### Data Model

```mermaid
erDiagram
    SearchQuery {
        uuid id PK
        uuid user_id FK
        string query
        string url_params
        enum source
        uuid parent_query_id FK
        bool active
        int run_count
        datetime last_run_at
        int total_jobs_found
        float avg_match_score
        int high_score_count
        datetime created_at
    }

    SearchQuery ||--o{ SearchQuery : "parent / children"
    SearchQuery ||--o{ Job : "found via"
```

### Computed Properties (not stored, derived at read time)

| Property | Formula | Purpose |
|---|---|---|
| `performance_score` | `avg_match_score × (high_score_count / total_jobs_found) × min(1, total_jobs_found / 10)` | Composite quality + volume metric. Saturates at 10 jobs. |
| `is_stale` | never run **or** `last_run_at` > 24h ago | Drives the "Run Stale" batch button |
| `is_low_performer` | run ≥ 3× **and** (avg < 35 **or** total < 2 jobs) | Highlighted yellow in UI; candidates for replacement |

### Query Sources

| Source | How Created |
|---|---|
| `imported` | Scraped from your Upwork saved searches page |
| `seeded` | Rule-generated from profile: each skill, skill pairs, title, domain extras |
| `ai_generated` | GPT-suggested based on top performers + past winning jobs |
| `manual` | Typed by you directly in the Query Library |

---

## Layer 2 — Seeding From Upwork Saved Searches

Your Upwork saved searches represent the search strategies you've already deliberately designed. They're imported as-is — same keywords, same filters — and become the **baseline the Lab will measure and improve**.

```mermaid
sequenceDiagram
    participant U as User (sidebar)
    participant BG as Background Script
    participant CS as Content Script
    participant API as UpApply API

    U->>BG: IMPORT_UPWORK_SAVED_SEARCHES
    BG->>CS: Open upwork.com/nx/search/jobs/saved searches page
    CS->>CS: Scrape { query, url_params, label } per saved search
    CS->>BG: Return scraped searches
    BG->>U: Forward results
    U->>API: POST /search-queries/bulk-import
    API->>API: Normalize + deduplicate against library
    API->>U: Return newly added queries
```

**Default URL parameters** applied to all searches: `contractor_tier=2,3&proposals=0-4`
(intermediate/expert tier; low-competition jobs with few proposals)

---

## Layer 3 — Search Execution Pipeline

Every query runs through the same pipeline whether triggered manually, in bulk, or by the Search Lab experiments.

```mermaid
sequenceDiagram
    participant UI as History / Search Labs UI
    participant BG as Background Script
    participant CS as Content Script (Upwork tab)
    participant API as UpApply API

    UI->>BG: SEARCH_UPWORK_JOBS { query, urlParams }
    BG->>CS: Navigate to upwork.com/nx/search/jobs/?q=...&urlParams
    CS->>CS: extractAllJobCards() — paginate up to 50 pages
    note over CS: article[data-test="JobTile"] per card<br/>fields: id, url, title, description,<br/>jobType, experienceLevel, clientInfo
    CS->>BG: Return ScrapedJobCard[]
    BG->>UI: Forward results

    UI->>API: POST /jobs/bulk-import (source=search, search_query_id)
    API->>API: Score each job against profile<br/>(match_score, chips, deal-breakers)
    API->>UI: Return scored jobs

    UI->>API: POST /search-queries/{id}/record-run
    note over API: jobs_found, avg_score, high_score_count<br/>Rolling weighted average update
    API->>UI: Updated query stats
```

**Scored jobs surface in the Find tab**, filterable by score threshold (≥90 / ≥70 / ≥50) and skill chips, sortable by score, recency, or your star rating.

---

## Layer 4 — Search Labs: Coverage Evaluation

*"Are my queries finding the jobs I know I should be targeting?"*

Coverage evaluation uses your **proven wins** as ground truth — jobs from Won Contracts imports and proposals that got a response or hire — and tests whether your current query set would have *found* those jobs.

```mermaid
flowchart TD
    START([User clicks Coverage]) --> WINS

    WINS["Collect target jobs<br/>(Won contracts + responded/hired proposals)"]
    WINS --> TOKENIZE

    TOKENIZE["Tokenize each active query<br/>(strip stop words, normalize)"]
    TOKENIZE --> MATCH

    MATCH["Match each target job's title + description<br/>against all query token sets"]
    MATCH --> SCORE

    SCORE{{"For each query:<br/>coverage_count, coverage_pct,<br/>sample_matches"}}

    SCORE --> COVERED["Covered jobs ✓"]
    SCORE --> GAPS["Gap jobs — wins no query would find"]

    GAPS --> GPT["GPT: generate 5 targeted queries<br/>covering gap jobs<br/>(with reasoning + suggested url_params)"]
    GPT --> SUGGEST["Display suggestions with<br/>gap_jobs_targeted, rate filters"]

    SUGGEST --> ADD[User clicks + Add]
    ADD --> LIBRARY["New query added to Library"]
```

**Coverage result includes:**
- Overall coverage % with a visual bar
- Per-query breakdown (how many wins each query covers)
- Up to 5 uncovered win titles
- 5 AI-suggested queries with reasoning and the specific gap jobs they'd target

---

## Layer 5 — Search Labs: Experiment → Grade → Optimize Loop

*"Of the queries I'm running, which ones are working? What should replace the weak ones?"*

```mermaid
flowchart LR
    QUERIES["All active queries\nin library"] --> RUN

    RUN["Run experiments:\nexecute each query live\non Upwork"] --> RESULTS

    RESULTS["QueryExperimentResult per query:\njobs_returned, avg_score,\nhigh_score_count"] --> GRADE

    GRADE{{"Grade each query"}}

    GRADE -- "hit_rate ≥ 30%\nand vol ≥ 5" --> STRONG["strong ✓\nno changes needed"]
    GRADE -- "jobs < 5\nhit_rate OK" --> LOWVOL["low_volume ⚠\ntoo narrow"]
    GRADE -- "hit_rate < 30%\nvol OK" --> LOWQUAL["low_quality ⚠\ntoo generic"]
    GRADE -- "both problems" --> BOTH["both ✗\nwrong angle"]

    LOWVOL --> VARIANTS
    LOWQUAL --> VARIANTS
    BOTH --> VARIANTS

    VARIANTS["GPT generates 2–3 variants\nper weak query"]

    VARIANTS --> BROADER["broader:\nremove constraints,\ngeneralize angle"]
    VARIANTS --> NARROWER["narrower:\nadd domain context,\nniche terms, role framing"]
    VARIANTS --> REFRAME["reframe:\ncompletely different angle"]

    BROADER --> USER
    NARROWER --> USER
    REFRAME --> USER

    USER{{"User decision\nper variant"}}
    USER -- Replace --> DELETE["Delete weak original\nAdd variant"]
    USER -- Add --> KEEP["Keep original\nAdd variant as supplement"]

    DELETE --> LIBRARY["Updated Library"]
    KEEP --> LIBRARY
    STRONG --> LIBRARY

    LIBRARY --> RUN
```

### Grade Definitions

| Grade | Condition | Strategy |
|---|---|---|
| **strong** | hit_rate ≥ 30% and jobs_returned ≥ 5 | Keep as-is |
| **low_volume** | jobs_returned < 5 | Make **broader** — fewer required words, more general framing |
| **low_quality** | high_score_count / jobs_returned < 30% | Make **narrower** — add domain context, specificity |
| **both** | low volume AND low quality | **Reframe** — completely different search angle |

---

## Complete End-to-End Flow

```mermaid
sequenceDiagram
    actor You
    participant Upwork
    participant Library as Query Library
    participant Lab as Search Labs
    participant Find as Find Tab

    Note over You,Find: Initial seeding
    You->>Upwork: Import Saved Searches
    Upwork->>Library: { query, url_params } × N
    Library->>Library: Profile-seeded + AI-generated queries added

    Note over You,Find: Regular usage — Run Stale
    You->>Library: Click "Run Stale (N)"
    Library->>Upwork: Execute each query (pagination)
    Upwork->>Find: Scored job results appear
    Library->>Library: Update avg_score, run_count per query

    Note over You,Find: Search Labs — Coverage check
    You->>Lab: Click Coverage
    Lab->>Library: Evaluate queries vs. winning jobs
    Lab->>You: Show % covered, gap jobs, suggestions
    You->>Library: Add suggested gap-covering queries

    Note over You,Find: Search Labs — Optimize cycle
    You->>Lab: Click Run (experiments)
    Lab->>Upwork: Run all queries live
    Lab->>Lab: Grade: strong / low_volume / low_quality / both
    You->>Lab: Click Optimize weak queries
    Lab->>You: Show broader/narrower/reframe variants
    You->>Library: Replace weak queries with variants

    Note over You,Find: Improved queries → better Find results
    Library->>Find: Higher quality jobs, higher match scores
```

---

## Query Lifecycle

```mermaid
stateDiagram-v2
    [*] --> New : imported / seeded / ai_generated / manual

    New --> Stale : never run\n(is_stale = true)
    Stale --> Active : first run
    Active --> Stale : >24h since last run

    Active --> LowPerformer : run ≥3×\nand avg<35 or <2 jobs
    LowPerformer --> Active : user replaces with variant\nor runs again with new data

    Active --> Inactive : user deletes (soft delete)
    LowPerformer --> Inactive : user deletes / replaces

    Inactive --> [*]
```

---

## Key Design Decisions

**Why your Upwork saved searches are the starting point:**
They represent deliberate choices about how you believe clients search for your skills. Rather than discarding them and starting fresh, the system treats them as hypotheses to be tested empirically. If they perform well, great. If they don't, the Lab tells you why and suggests improvements.

**Why the system biases toward inclusivity (broader over narrower):**
The cost of missing a good job is higher than the cost of seeing an irrelevant one. Low-volume queries are penalized harder. The optimization prompt explicitly instructs GPT to favor finding more good jobs over perfect precision.

**Why performance_score saturates at 10 jobs:**
A query returning 3 jobs all at 90 score is more useful than one returning 100 jobs at average 40. The formula rewards quality-per-job, not raw volume, while still requiring minimum volume before trusting the quality signal.

**Why parent_query_id exists:**
Variants created via optimization are linked back to the original weak query. This enables future analytics on which optimization strategies actually produced better results over time.

---

## Current Status

| Component | Status |
|---|---|
| Query Library (CRUD, stats, seed, generate) | ✅ Production |
| Bulk import from Upwork saved searches | ✅ Production |
| Single query run + stat recording | ✅ Production |
| Run all stale batch | ✅ Production |
| Search Labs: Coverage evaluation | ✅ Production |
| Search Labs: Experiment + Grade + Optimize | ✅ Production |
| Find tab with score/chip/rating filters | ✅ Production |
| Saved Jobs page badge scorer (notifications pattern) | 🔜 Planned (see plan file) |
