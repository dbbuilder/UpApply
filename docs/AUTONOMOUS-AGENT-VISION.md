# UpApply Autonomous Agent Vision
*Authored: 2026-04-12*

---

## The Core Idea

UpApply should behave the way a great human assistant would on their first day, first week, first month, and first year. On day one they watch, ask questions, and learn your preferences. By month three they're drafting everything and you're just approving. By year one they're running independently and you only see results.

The system must **earn** autonomy through demonstrated reliability at each stage — never assume it. And every user starts the same walk-before-run progression regardless of how mature the platform becomes, because the agent needs to learn *them* specifically before it acts *for* them.

---

## The Learning Loop

Every interaction produces a signal. The system learns from all of them.

```
┌─────────────────────────────────────────────────────────────┐
│                    THE LEARNING LOOP                        │
│                                                             │
│   SEARCH ──→ SCORE ──→ ASK ──→ LEARN                       │
│     ↑                           │                           │
│     │                           ↓                           │
│   RELEARN ←── WATCH ←── APPLY ←─┘                          │
│                                                             │
│   Every arrow is a feedback signal.                         │
│   Every signal makes the next loop better.                  │
└─────────────────────────────────────────────────────────────┘
```

### What Each Stage Learns

| Stage | Signal collected | What improves |
|-------|-----------------|---------------|
| **Search** | Which queries return high-quality jobs | Query weights, search adapter selection |
| **Score** | User approves/rejects suggestions | Score thresholds, deal-breaker detection |
| **Ask** | Approval reasons, rejection reasons | Preference model, inclusive scoring |
| **Apply** | Cover letter edits (what user changed) | Generation style, structure, banned phrases |
| **Watch** | Client viewed / responded / hired / ghosted | Which proposals patterns actually win |
| **Relearn** | Outcome mapped back to original job signal | Score calibration, proposal corpus |

---

## Design Principles

### 1. Inclusive before exclusive
The scoring model must bias toward surfacing jobs that *mostly* match rather than only jobs that *perfectly* match. A 70% match that the user approves is worth more as a learning signal than a 95% match the agent never showed. Missed opportunities cost real money. Over-filtering is a silent failure.

**Implementation:** Default threshold starts at 55 (not 75). User can tighten it. System auto-adjusts based on how many suggestions go approved vs rejected — if user rejects 80% of suggestions, tighten; if they approve 80%, loosen.

### 2. Writing quality is non-negotiable at every autonomy level
Even at full autonomy, every generated proposal passes through the existing quality pipeline — no "I" sentence starts, no banned phrases, no salutation, corpus-voice calibration, word count guard. Quality rules are not loosened as autonomy increases.

### 3. Earn autonomy, don't grant it
Each new autonomy level unlocks only when measurable reliability thresholds are met. The system can also *lose* autonomy if outcomes degrade. This is not a setting the user manually configures — it's a governance layer that manages itself.

### 4. Every new user starts at zero
No matter how good the platform gets at month 18 with 500 users, a new user on day one starts at Level 1. Their agent watches before it acts. The walk-before-run progression is mandatory, not optional. This protects the user's Upwork reputation during the learning period.

### 5. Modular adapters everywhere
Every external integration — job source, submission channel, feedback channel, generation model — is behind an adapter interface. Swap RSS for GraphQL, swap Claude for GPT, add Telegram approvals, add LinkedIn sourcing — none of these changes touch core agent logic.

### 6. Multi-user learning amplifies individual learning
Anonymized outcome signals pool across users with similar profiles. A new Python/FastAPI freelancer doesn't start cold — they inherit calibrated weights from others with similar skill signatures. Individual privacy is protected; only outcome patterns (not proposal text) flow into the shared pool.

---

## Autonomy Levels

```
LEVEL 1 — OBSERVER
  Agent: searches, scores, does nothing else
  User sees: weekly digest of scored jobs
  Learns: nothing yet — pure observation window
  Unlocks Level 2: user engages with 10+ scored jobs

LEVEL 2 — SUGGESTER
  Agent: adds high-scoring jobs to queue with reasoning
  User sees: Suggestions tab in extension, approve/reject
  Learns: approval patterns → score calibration
  Unlocks Level 3: ≥60% approval rate over 20 suggestions

LEVEL 3 — DRAFTER
  Agent: writes cover letter for every approved job
  User sees: draft in extension, edits before sending
  Learns: edit distance → generation style preferences
  Unlocks Level 4: avg edit distance <15% over 10 proposals

LEVEL 4 — ASSISTED
  Agent: submits proposal, user sees confirmation screen first
  User sees: "Ready to send — confirm?" with 60-second abort window
  Learns: which submissions get responses
  Unlocks Level 5: ≥25% response rate over 20 submissions

LEVEL 5 — AUTONOMOUS (monitored)
  Agent: searches, scores, drafts, submits within guardrails
  User sees: daily digest of actions taken
  Guardrails: bid cap, connects cap, proposal count/day cap
  Learns: full outcome cycle — response, hire, earnings
  Level 5 can downgrade to Level 4 if response rate drops below 15%

LEVEL 6 — OPTIMIZING
  Agent: runs controlled experiments (A/B proposal variants)
  User sees: performance dashboard, strategy recommendations
  Learns: causal attribution — which writing patterns → which outcomes
  Gate: never reached automatically; user must explicitly enable
```

---

## Architecture: Adapter-Based, Modular

```
┌───────────────────────────────────────────────────────────────┐
│  AGENT CORE (Anthropic SDK tool-use loop)                     │
│  Orchestrates: search → score → suggest → draft → submit      │
│  Governed by: AutonomyGovernor                                │
└──────────┬──────────┬────────────┬──────────┬─────────────────┘
           │          │            │          │
    ┌──────▼──┐  ┌────▼───┐  ┌────▼──┐  ┌───▼──────┐
    │ Search  │  │Scoring │  │Genera-│  │Feedback  │
    │Adapters │  │Adapters│  │tion   │  │Adapters  │
    │         │  │        │  │Adapters│ │          │
    │•RSS     │  │•Rules  │  │•Claude│  │•Extension│
    │•GraphQL │  │•LLM    │  │•GPT   │  │•Telegram │
    │•Saved Q │  │•Collab │  │•Fine- │  │•Email    │
    │•OpenClaw│  │ Filter │  │ tuned │  │•WhatsApp │
    └──────┬──┘  └────┬───┘  └────┬──┘  └───┬──────┘
           │          │            │          │
┌──────────▼──────────▼────────────▼──────────▼─────────────────┐
│  DATA LAYER (PostgreSQL + pgvector)                            │
│  jobs · job_queue · proposals · applications                   │
│  memories · outcome_events · user_autonomy_profiles           │
│  global_signal_pool (anonymized cross-user outcomes)          │
└───────────────────────────────────────────────────────────────┘
```

### Adapter Interfaces

```python
class ISearchAdapter(Protocol):
    async def fetch_jobs(self, query: SearchQuery, limit: int) -> list[RawJob]: ...
    async def health_check(self) -> bool: ...

class IScoringAdapter(Protocol):
    async def score(self, job: RawJob, profile: UserProfile) -> ScoredJob: ...
    async def calibrate(self, outcomes: list[Outcome]) -> None: ...

class IGenerationAdapter(Protocol):
    async def generate(self, job: ScoredJob, context: GenerationContext) -> Draft: ...
    async def update_style(self, edits: list[ProposalEdit]) -> None: ...

class ISubmissionAdapter(Protocol):
    async def submit(self, proposal: Proposal, autonomy_level: int) -> SubmitResult: ...

class IFeedbackAdapter(Protocol):
    async def request_approval(self, jobs: list[ScoredJob]) -> list[Approval]: ...
    async def notify(self, event: AgentEvent) -> None: ...
```

---

## New Database Tables Required

```sql
-- Autonomy progression per user
CREATE TABLE user_autonomy_profiles (
    user_id         UUID PRIMARY KEY REFERENCES users(id),
    level           INT NOT NULL DEFAULT 1,          -- 1-6
    level_since     TIMESTAMPTZ DEFAULT now(),
    suggestions_shown     INT DEFAULT 0,
    suggestions_approved  INT DEFAULT 0,
    proposals_submitted   INT DEFAULT 0,
    proposals_responded   INT DEFAULT 0,
    proposals_hired       INT DEFAULT 0,
    avg_edit_distance     FLOAT,                     -- 0.0-1.0
    last_evaluated  TIMESTAMPTZ,
    locked          BOOL DEFAULT false,              -- manual freeze
    score_threshold FLOAT DEFAULT 55.0              -- auto-adjusting
);

-- Pre-queue: agent suggestions awaiting user review
CREATE TABLE job_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    upwork_url      TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    skills          JSONB DEFAULT '[]',
    budget_amount   TEXT,
    budget_type     TEXT,
    client_info     JSONB,
    ai_score        FLOAT,
    ai_reasoning    TEXT,
    chips           JSONB DEFAULT '[]',
    status          TEXT DEFAULT 'suggested',
    -- suggested → approved | rejected | applied | expired
    source          TEXT DEFAULT 'agent',
    source_query_id UUID REFERENCES search_queries(id),
    rejection_reason TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    reviewed_at     TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ DEFAULT now() + interval '7 days',
    UNIQUE(user_id, upwork_url)
);

-- Full outcome event stream — every signal from every stage
CREATE TABLE outcome_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    event_type      TEXT NOT NULL,
    -- job_queued | job_approved | job_rejected | proposal_drafted |
    -- proposal_edited | proposal_submitted | proposal_viewed |
    -- proposal_responded | contract_started | contract_completed |
    -- contract_ended_early | hired | not_hired
    job_url         TEXT,
    job_queue_id    UUID REFERENCES job_queue(id),
    proposal_id     UUID REFERENCES proposals(id),
    application_id  UUID REFERENCES applications(id),
    payload         JSONB,                           -- event-specific data
    ai_score_at_event FLOAT,                         -- score when this happened
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Anonymized global signal pool for cross-user learning
CREATE TABLE global_signal_pool (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_signature TEXT NOT NULL,                   -- hashed skill vector
    job_type        TEXT,                            -- from chips
    budget_bracket  TEXT,                            -- <$1k / $1k-5k / $5k+
    ai_score        FLOAT,
    outcome         TEXT,                            -- responded / hired / ghosted
    proposal_length INT,                             -- word count
    days_to_outcome INT,
    created_at      TIMESTAMPTZ DEFAULT now()
    -- no user_id, no proposal text, no job title
);
```

---

## The Autonomy Governor

The governor runs after every batch of outcomes and decides whether to advance, hold, or downgrade a user's autonomy level.

```python
class AutonomyGovernor:
    """
    Evaluates user's outcome history and manages their autonomy level.
    Runs daily. Can advance OR downgrade.
    """

    UNLOCK_CONDITIONS = {
        2: lambda p: p.suggestions_shown >= 10,
        3: lambda p: p.approval_rate >= 0.60 and p.suggestions_shown >= 20,
        4: lambda p: p.avg_edit_distance <= 0.15 and p.proposals_drafted >= 10,
        5: lambda p: p.response_rate >= 0.25 and p.proposals_submitted >= 20,
        6: lambda p: False,  # Never auto-unlock; user opts in explicitly
    }

    DOWNGRADE_CONDITIONS = {
        5: lambda p: p.response_rate < 0.15 and p.proposals_submitted >= 10,
        4: lambda p: p.approval_rate < 0.30 and p.suggestions_shown >= 30,
    }

    async def evaluate(self, user_id: str) -> AutonomyDecision:
        profile = await get_autonomy_profile(user_id)
        current = profile.level

        # Check downgrade first
        if current in self.DOWNGRADE_CONDITIONS:
            if self.DOWNGRADE_CONDITIONS[current](profile):
                return AutonomyDecision(
                    action="downgrade",
                    from_level=current,
                    to_level=current - 1,
                    reason="Response rate below threshold",
                )

        # Check advance
        next_level = current + 1
        if next_level in self.UNLOCK_CONDITIONS:
            if self.UNLOCK_CONDITIONS[next_level](profile):
                return AutonomyDecision(
                    action="advance",
                    from_level=current,
                    to_level=next_level,
                    reason=f"Unlocked level {next_level} thresholds",
                )

        return AutonomyDecision(action="hold", from_level=current, to_level=current)
```

---

## Cross-User Learning: How It Works

Users with similar skill signatures benefit from each other's outcomes — without sharing any personal data.

```
User A (Python/FastAPI/AI, 5 years):
  Applied to 50 jobs → 12 responses → 4 hires
  Winning pattern: budget >$2k, AI chip, <400 word proposals
  → anonymized into global_signal_pool

New User B (Python/FastAPI/ML, 3 years):
  skill_signature matches User A's bucket
  → Scoring calibration bootstrapped from User A's win patterns
  → Score threshold initialized to 62 (not 55) because similar profiles
     showed lower quality at 55
  → Generation adapter pre-tuned to <400 words for AI jobs

User B walks the same progression (Level 1 → 2 → ...) but starts
with better-calibrated priors instead of cold start.
```

The skill signature is a hashed bucketing of skills + seniority + rate range — not a unique identifier.

---

## The Profitability Engine

The agent must optimize for Upwork success, not just activity. Key design choices:

**Inclusive scoring over exclusive:**
- Surface jobs at 55+ (not 75+) to maximize learning signal
- False negatives (good jobs not shown) cost real money
- User rejection at 65 is more valuable than missing a 78 entirely

**Connects management:**
- Never auto-spend connects without checking `available_connects`
- Stop submitting when connects < (2 × avg_connects_per_bid) as reserve buffer
- Alert user to buy connects before the agent runs dry

**Bid calibration:**
- Track win rate by bid amount relative to client budget
- Learn the user's personal sweet spot (not generic "bid 10% below budget")
- Gradually adjust `preferred_bid` up as win rate justifies it

**Proposal timing:**
- Track time-of-post vs response rate (jobs posted <6h old get higher response rates)
- Agent prioritizes fresh jobs in each search run

**Quality over quantity:**
- Cap at 5 autonomous submissions per day regardless of connects
- Better to submit 3 excellent proposals than 10 mediocre ones
- Monitor response-per-proposal; if it drops, pause and surface to user

---

## Sprint Strategy: Walk Before Run

### Foundation Principle
Each sprint delivers a **working, shippable increment**. No sprint is only infrastructure. Every sprint's output can be used by Chris and validated before the next begins.

---

### Sprint 1 — Walk: Search + Surface (2 weeks)
**Goal:** Agent finds jobs and shows them. Nothing else.

Deliverables:
- `job_queue` table + migration
- `POST/GET /api/v1/job-queue` endpoints
- Upwork RSS search adapter (reads from saved search_queries URL params)
- `JobDiscoveryAgent` — Level 1 + 2 behavior: fetch → score → add to queue
- Extension "Suggestions" tab — read-only list of queued jobs with score + chips + AI reasoning
- Render cron job: daily 6am PT run per active user

What the agent learns: nothing yet — observation only.
Success metric: agent surfaces 10–20 relevant jobs per day without Chris lifting a finger.

---

### Sprint 2 — Walk: Feedback + Calibration (2 weeks)
**Goal:** User approves/rejects suggestions. Agent learns what to show.

Deliverables:
- Approve/Reject actions in Suggestions tab
- `rejection_reason` picker (budget too low / not my niche / client looks bad / other)
- `outcome_events` table + ingestion
- `user_autonomy_profiles` table + Level 1→2 unlock logic
- Score threshold auto-adjustment (approval rate feedback loop)
- `AutonomyGovernor` — runs daily, evaluates level progression
- "Agent learned X from your last 10 decisions" weekly summary in extension

What the agent learns: which jobs to surface, which to skip, score threshold calibration.
Success metric: approval rate improves from baseline toward 60%+ over 2 weeks.

---

### Sprint 3 — Jog: Draft Generation (2 weeks)
**Goal:** Agent writes the letter. User edits and sends manually.

Deliverables:
- Auto-generate cover letter draft for every approved job (existing pipeline, triggered on approval)
- "Draft ready" notification in extension
- Side-by-side diff view: AI draft vs user's edits
- Edit distance tracking → stored in `outcome_events`
- Level 2→3 unlock: approval rate ≥60% over 20 suggestions
- Level 3→4 gate setup: track edit distance over 10 proposals

What the agent learns: user's writing style preferences, structure preferences, sections they always rewrite.
Success metric: average edit distance <25% by end of sprint (user keeping most of the letter).

---

### Sprint 4 — Jog: Assisted Submission (2 weeks)
**Goal:** Agent fills the form. User confirms before send.

Deliverables:
- Extension auto-fill on approved + drafted proposals (existing auto-fill, triggered automatically)
- "Ready to send — confirm?" modal with 60-second countdown + abort
- Submission tracking: store connects spent, bid amount, timestamp
- Post-submit monitoring: check proposal status every 24h (via GraphQL)
- Response/view events → `outcome_events`
- Level 3→4 unlock: avg edit distance <15% over 10 proposals

What the agent learns: which submissions get viewed, which get responded to.
Success metric: proposal response rate measurable and tracked; user comfortable with the flow.

---

### Sprint 5 — Run: Autonomous Submission (2 weeks)
**Goal:** Agent submits within guardrails. User sees digest.

Deliverables:
- Level 4→5 unlock: ≥25% response rate over 20 submissions
- Level 5 execution: full search → score → draft → submit loop
- Hard guardrails: bid cap, connects reserve, proposals/day cap (5)
- Daily digest notification (extension + optional email): "submitted 3 proposals today"
- Downgrade trigger: response rate <15% → drop to Level 4, alert user
- Connects management: check balance before each run, alert when low

What the agent learns: end-to-end outcome attribution — which search queries → which jobs → which proposals → which hires.
Success metric: Chris can leave town for a week and UpApply keeps working.

---

### Sprint 6 — Run: Learning Engine (2 weeks)
**Goal:** Outcomes feed back into everything.

Deliverables:
- Outcome ingestion pipeline: scrape proposal status changes, contract starts, contract ends
- Winning proposal → memory: hired proposals auto-added to corpus with `importance=0.95`
- Score calibration: adjust `global_signal_pool` with Chris's outcome data
- Per-user ROI dashboard: connects spent, proposals submitted, responses, hires, estimated earnings
- Cross-user learning bootstrap: anonymized outcomes → `global_signal_pool`
- New user cold-start: initialize score threshold + generation style from similar skill bucket

What the agent learns: full causal chain — what score predicted win vs what actually won.
Success metric: response rate improves measurably from Sprint 4 baseline.

---

### Sprint 7 — Scale: Multi-User + Optimization (3 weeks)
**Goal:** Second user experience is better than first. Platform learns faster over time.

Deliverables:
- New user onboarding flow: "walk before run" is enforced, level shown in UI
- Collaborative filtering: new users with similar profiles inherit calibrated priors
- A/B proposal variants (Level 6 only, opt-in): agent generates 2 versions, tracks which performs better
- Search query optimization: auto-generate new queries from winning job patterns (existing search_lab)
- OpenClaw integration (optional): Telegram/WhatsApp approval channel for mobile users
- Admin dashboard: aggregate stats across all users (anonymized), platform health

What the platform learns: which onboarding patterns lead to fastest autonomy progression; which skill profiles perform best on which job types.
Success metric: second user reaches Level 3 in half the time it took Chris.

---

## What Full Autonomy Actually Looks Like

At Level 5, a normal day looks like this:

```
6:00am PT — Cron triggers JobDiscoveryAgent for each active user
  → Fetches jobs from all saved search queries (RSS adapters)
  → Scores each job (LLM scoring + rule-based blend)
  → Checks job_queue for duplicates
  → Adds qualifying jobs (score ≥ threshold) to queue
  → Generates cover letter drafts for jobs in queue

6:30am PT — AutonomyGovernor evaluates each user's profile
  → Advances, holds, or downgrades autonomy level
  → For Level 5 users: triggers ProposalSubmissionAgent

7:00am PT — ProposalSubmissionAgent (Level 5 only)
  → Reads approved + drafted jobs from queue
  → Checks connects balance
  → Submits up to 5 proposals within bid caps
  → Records all submission events

12:00pm PT — OutcomeMonitorAgent
  → Scrapes proposal statuses
  → Records views, responses, invites
  → Updates outcome_events

8:00pm PT — Daily digest assembled
  → Sent to extension (badge count) + email (optional)
  → "Today: 3 submitted, 1 viewed, 1 new response from Monday"

Weekly — LearningAgent
  → Processes week's outcome_events
  → Updates score calibration
  → Promotes winning proposals to corpus
  → Adjusts search query weights
  → Anonymizes outcomes → global_signal_pool
```

Chris sees a digest. He can intervene at any time. But the default is: it runs.

---

## Technology Stack for the Agent Layer

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Agent loop | Raw Anthropic SDK (tool-use) | Full control, cost transparency, fits FastAPI |
| LLM | Claude Sonnet 4.6 | Cover letter quality, instruction following |
| Scoring LLM | gpt-4o-mini | Cheap, fast, structured JSON output |
| Scheduling | Render Cron Service | Already on Render, no new infrastructure |
| Search | Upwork RSS → GraphQL (later) | RSS is unauthenticated and immediately available |
| Feedback channel (v1) | Extension sidebar | Already built |
| Feedback channel (v2) | OpenClaw (Telegram/WhatsApp) | Mobile approvals without opening laptop |
| State/memory | PostgreSQL + pgvector | Already exists, already proven |
| Workflow (Stage 2) | LangGraph | Stateful, checkpointed, human-in-loop gates |
| Observability | Render logs + Sentry (existing) | Already configured |

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Agent submits low-quality proposal autonomously | Upwork reputation damage | Quality pipeline runs at every level; edit distance gate before Level 4 |
| OpenAI/Anthropic quota exhaustion during run | Agent loop fails silently | Existing fallback to rule-based scoring; alert email on quota hit |
| Upwork changes RSS/GraphQL schema | Search breaks | Adapter pattern: swap to alternative source without touching agent core |
| User never engages, stays at Level 1 forever | No learning signal | Re-engagement email after 7 days; show "you missed X jobs this week" |
| Over-spending connects autonomously | Financial harm | Hard connects reserve check before every submission; user-set daily cap |
| Cross-user learning leaks private data | Privacy/trust issue | global_signal_pool contains only hashed signatures + outcome codes, never text |
| Agent submits to jobs user explicitly disliked | Trust erosion | Rejected URLs stored; agent checks before queuing; rejection reason fed to scorer |

---

## Success Metrics (Platform Level)

| Metric | Target at 6 months | Target at 12 months |
|--------|--------------------|---------------------|
| Avg days to Level 3 (Drafter) | <14 days | <7 days |
| Avg days to Level 5 (Autonomous) | <60 days | <30 days |
| Platform response rate (proposals responded / submitted) | >20% | >30% |
| Platform hire rate (hired / submitted) | >8% | >12% |
| User retention at 90 days | >60% | >75% |
| Agent-generated proposals accepted without edit | >50% | >70% |
| Connects ROI ($ earned / connects spent) | Measurable | Improving |
