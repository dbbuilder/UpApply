# Job-fit rubric — plan

Status: proposal (2026-11-04). Nothing here is built. Building it waits on Chris (NEXT.md, Decisions pending).

## Why the current score misleads

Measured on 2026-11-02 against the production scan data and the real scoring code:

- `run_full_analysis` blends `0.7 × LLM score + 0.3 × rule score` (`api/app/services/job_analysis.py`).
- Jobs from the search-page scan carry no skills list (stored as `[]`). With no skills, `calculate_match_score` starts from a fixed 50 instead of a skill ratio, then adds memory relevance, profile completeness and a constant 15. For Chris it returns 85–94 for any scanned job (reproduced by importing the function: 85.2 / 89.8 / 94.2 at memory similarity 0.3 / 0.45 / 0.6).
- So a scanned job's score is roughly `0.7 × grade + 27`. An LLM grade of 40 (the prompt's own "weak fit" band) becomes 54.9; the Strapi CMS job graded about 45 became 58.5. The 55 threshold therefore admits weak fits.
- The LLM half is one integer from `gpt-5.4-nano` with an 80-token reply, over the title, the first 1,500 characters of the description and up to 5 past wins. It has no notion of the role level Chris actually wins: of 194 proposals, the 5 with any response were all fractional CTO, technical lead or advisory roles.

## Goal

A score whose order matches Chris's own judgement: the top of Pending should be jobs he would apply to, sales and assistant roles should never clear the threshold, and each score should say why.

## The rubric

Each dimension is graded 0–4 against written anchors. The final score is `25 × Σ(weight × grade) / Σ(weight)`, so 0–100. A dimension with no data is graded 2 (neutral), never 4.

| Dimension | Weight | Graded by | 4 means | 0 means |
|---|---|---|---|---|
| Role level | 30 | LLM | the role the user targets (from `preferred_project_types` / `career_goals`; for Chris: fractional/interim CTO, technical co-founder, advisory, due diligence) | not a technical role (sales, assistant, marketing) |
| Stack and domain | 20 | LLM (plus skill match when the job has skills) | core of the user's stack and a domain they have shipped in | a stack or field the user has never worked in |
| Evidence | 15 | code: best cosine between the job and the user's approved facts | strong match (≥ 0.55) | none (< 0.30); thresholds set from the eval |
| Engagement | 20 | code: budget against the user's minimums | hourly top ≥ 1.5 × minimum, or fixed ≥ 3 × minimum | below the minimum (already pre-filtered) |
| Competition and timing | 15 | code: proposals bucket and posted age | under 5 proposals, posted within a day | 50+ proposals, or near the lookback limit |

Red flags cap the score at 30 whatever the sum: commission-only or equity-only pay, an unpaid test task, a non-technical role, or agency staffing (reselling the user's hours). The LLM reports them as codes; regexes catch the obvious wording.

The client trust card stays separate (decision of #46): client history never changes the match score.

The LLM call returns JSON: `{role_level: {grade, reason}, stack_domain: {grade, reason}, red_flags: [codes]}`, one reason of at most 100 characters each. That is about 150 output tokens instead of 80, still one call per job. The code computes the other three dimensions and the total.

Anchors are written per dimension with two or three example job titles each, taken from the stored scan jobs, so the small model grades against concrete cases. They are built from the user's profile, not hard-coded for Chris, so Gus gets his own targets.

## Measuring it before it ships

`scripts/eval_job_fit.py`, read-only against production, writing to `docs/evals/` (never committed):

1. **Eval set:** the stored scanned jobs (325 on 2026-11-02), plus the jobs behind the 194 imported proposals.
2. **Labels:** Chris marks 40 jobs apply / maybe / skip on a review page: 20 from today's top of Pending, 10 from just below the threshold, and 10 at random.
3. **Score both ways:** today's score and the rubric, the latter with both `gpt-5.4-nano` and `claude-haiku-4-5` (pick the model on agreement and cost).
4. **Pass when:**
   - at least 14 of the rubric's top 20 are labelled apply or maybe (today's top 20 is measured the same way, for comparison);
   - no job with a sales, assistant or marketing title clears the threshold;
   - the 5 jobs with responses rank in the top quarter.

Done when: the script runs, the label page is filled, and the report shows both scores side by side.

## Rollout

1. **Shadow.** The ingest stores the rubric score beside the current one for a week of scans; the sidebar keeps showing the current score. Done when: every new scanned job has both scores.
2. **Storage.** Showing "why" in the sidebar needs the per-dimension breakdown stored. `job_queue` has no JSON column for it, so this is migration 029 (`job_queue.score_breakdown JSONB`, nullable). Without the migration, only a one-line summary fits in `ai_reasoning`. Recommended: add it.
3. **Switch.** `ai_score` becomes the rubric score for scanned jobs and for `POST /jobs/analyze`. The rule score no longer counts when a job has no skills list. Done when: tests cover the switch and the old blend is gone.
4. **Threshold.** Re-set `score_threshold` from the shadow week: the lowest score at which at least half of labelled jobs were apply or maybe. Done when: the new threshold is recorded with the numbers behind it.

## Phases

1. Eval harness and labels; no production change.
2. `api/app/services/job_fit.py`: anchors built from the profile, the LLM call, the code dimensions, red-flag caps; unit tests over the anchor examples. Shadow mode in the ingest.
3. Migration 029 and the sidebar breakdown ("Role: CTO advisory (4) · Budget $120/hr (4) · 50+ proposals (1)").
4. Switch and threshold.

Each phase is one PR. Done when, overall: the eval passes, the switch is live, and the threshold is reset.

## Questions for Chris

1. Weights: role level 30, stack and domain 20, engagement 20, evidence 15, competition and timing 15. Change any?
2. Should competition count at all? A 50+ proposal job you are perfect for may still be worth sending.
3. Model: keep the OpenAI nano model if it agrees with your labels, or move scoring to Claude Haiku?
4. Migration 029 for the breakdown: yes or no?
