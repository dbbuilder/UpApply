"""JobDiscoveryAgent — Anthropic tool-use loop for discovering and queuing jobs.

The agent:
  1. Gets the user's active search queries
  2. Fetches jobs from Upwork RSS for each query
  3. Deduplicates against job_queue + jobs tables
  4. Scores each candidate job via the existing /api/v1/jobs/analyze endpoint
  5. Adds qualifying jobs (score >= threshold, default 55) to the queue
  6. Caps new additions at 15 per run

The agent uses the raw Anthropic SDK tool-use loop. Each tool is an async
function that calls the UpApply API via httpx (using a service JWT).

Usage:
    from agent.job_discovery import JobDiscoveryAgent
    agent = JobDiscoveryAgent(api_base="https://upapply-api.onrender.com", token="...")
    result = await agent.run(user_id="uuid-here")
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import anthropic
import httpx

from agent.rss_adapter import fetch_jobs_from_rss

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

DISCOVERY_MODEL = "claude-sonnet-4-6"
MAX_QUEUED_PER_RUN = 15
DEFAULT_SCORE_THRESHOLD = 55.0

SYSTEM_PROMPT = """\
You are the UpApply Job Discovery Agent. Your job is to find relevant freelance
opportunities for a user and add the best ones to their suggestion queue.

WORKFLOW (follow this order every run):
1. Call get_search_queries to get the user's active Upwork search queries.
2. For each query, call fetch_jobs_from_rss to retrieve recent job postings.
3. For each job, call check_already_queued to skip duplicates.
4. For jobs not yet seen, call analyze_job to score them against the user profile.
5. For jobs scoring >= {threshold}, call add_to_queue with a clear ai_reasoning.
6. Stop once you've added {max_jobs} new jobs, or exhausted all queries.

SCORING GUIDANCE:
- Be inclusive. Score threshold is {threshold} (not 75). Surface jobs that mostly match.
- Missed opportunities cost real money. When uncertain, score and add.
- Provide specific ai_reasoning: cite which skills match, what the client needs, why it fits.
- Include relevant chips from: python, fastapi, react, typescript, sql, postgresql, azure,
  aws, ai, llm, saas, mvp, cto, advisory, fullstack, data, automation, backend, frontend.

CHIP SELECTION:
- Only include chips that genuinely apply to the job posting.
- Prefer specificity over volume. 2-4 chips is typical; 6 is the maximum.

EFFICIENCY:
- Process queries in order of likely relevance.
- Skip any job with check_already_queued returning true.
- Stop adding jobs once {max_jobs} new queue entries are created this run.
- You may call multiple RSS fetches in a row before scoring — batch if helpful.
"""


# --------------------------------------------------------------------------
# Result dataclass
# --------------------------------------------------------------------------

@dataclass
class DiscoveryResult:
    """Summary returned after a discovery run."""

    user_id: str
    jobs_fetched: int
    jobs_skipped_duplicate: int
    jobs_scored: int
    jobs_queued: int
    errors: list[str]


# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------

class JobDiscoveryAgent:
    """Anthropic tool-use loop that discovers and queues Upwork jobs for a user."""

    def __init__(self, api_base: str, token: str) -> None:
        self.api_base = api_base.rstrip('/')
        self.token = token
        self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        self._http: Optional[httpx.AsyncClient] = None

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def _api_get(self, path: str) -> Any:
        assert self._http is not None
        resp = await self._http.get(f"{self.api_base}{path}", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def _api_post(self, path: str, body: dict) -> Any:
        assert self._http is not None
        resp = await self._http.post(
            f"{self.api_base}{path}",
            json=body,
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ── Tool implementations ───────────────────────────────────────────────

    async def _tool_get_search_queries(self) -> str:
        """Return a JSON list of active search queries for the current user."""
        queries = await self._api_get("/api/v1/search-queries")
        active = [
            {
                "id": q["id"],
                "query": q["query"],
                "url_params": q.get("url_params") or f"q={q['query'].replace(' ', '+')}",
            }
            for q in queries
            if q.get("active", True)
        ]
        return json.dumps(active)

    async def _tool_fetch_jobs_from_rss(self, url_params: str, limit: int = 20) -> str:
        """Fetch jobs from the Upwork RSS feed for given url_params."""
        jobs = await fetch_jobs_from_rss(url_params, limit=limit)
        result = [
            {
                "title": j.title,
                "description": j.description[:800],
                "upwork_url": j.upwork_url,
                "skills": j.skills,
                "budget_amount": j.budget_amount,
                "budget_type": j.budget_type,
                "posted_date": j.posted_date.isoformat() if j.posted_date else None,
            }
            for j in jobs
        ]
        self._stats["jobs_fetched"] += len(result)
        return json.dumps(result)

    async def _tool_check_already_queued(self, upwork_url: str) -> str:
        """Check if the given job URL is already in the queue or jobs table.

        Returns JSON {"already_exists": bool}.
        """
        # Check job_queue (all statuses)
        queue_items = await self._api_get(f"/api/v1/job-queue?limit=200")
        for item in queue_items:
            if item.get("upwork_url") == upwork_url:
                self._stats["jobs_skipped_duplicate"] += 1
                return json.dumps({"already_exists": True, "reason": "in_queue"})

        # Check jobs table (previously scored/saved jobs)
        try:
            jobs = await self._api_get(f"/api/v1/jobs")
            for job in jobs:
                if job.get("upwork_url") == upwork_url:
                    self._stats["jobs_skipped_duplicate"] += 1
                    return json.dumps({"already_exists": True, "reason": "in_jobs"})
        except Exception:
            pass  # Non-critical — proceed if jobs check fails

        return json.dumps({"already_exists": False})

    async def _tool_analyze_job(
        self,
        title: str,
        description: str,
        upwork_url: str,
        skills: Optional[list] = None,
        budget_amount: Optional[str] = None,
    ) -> str:
        """Score a job against the user's profile via the analyze endpoint."""
        payload = {
            "title": title,
            "description": description,
            "upwork_url": upwork_url,
            "skills_required": skills or [],
            "budget_amount": budget_amount,
        }
        try:
            result = await self._api_post("/api/v1/jobs/analyze", payload)
            self._stats["jobs_scored"] += 1
            return json.dumps({
                "match_score": result.get("match_score", 0),
                "skill_matches": result.get("skill_matches", []),
                "missing_skills": result.get("missing_skills", []),
                "strengths": result.get("strengths", []),
                "concerns": result.get("concerns", []),
                "deal_breaker_warnings": result.get("deal_breaker_warnings", []),
            })
        except Exception as exc:
            logger.warning("analyze_job failed for %s: %s", upwork_url, exc)
            return json.dumps({"match_score": 0, "error": str(exc)})

    async def _tool_add_to_queue(
        self,
        upwork_url: str,
        title: str,
        description: str,
        skills: Optional[list] = None,
        budget_amount: Optional[str] = None,
        budget_type: Optional[str] = None,
        ai_score: float = 0.0,
        ai_reasoning: str = "",
        chips: Optional[list] = None,
        source_query_id: Optional[str] = None,
    ) -> str:
        """Add a qualifying job to the user's suggestion queue."""
        if self._stats["jobs_queued"] >= MAX_QUEUED_PER_RUN:
            return json.dumps({"success": False, "reason": "cap_reached"})

        payload = {
            "upwork_url": upwork_url,
            "title": title,
            "description": description,
            "skills": skills or [],
            "budget_amount": budget_amount,
            "budget_type": budget_type,
            "ai_score": ai_score,
            "ai_reasoning": ai_reasoning,
            "chips": chips or [],
            "source": "agent",
            "source_query_id": source_query_id,
        }
        try:
            result = await self._api_post("/api/v1/job-queue", payload)
            self._stats["jobs_queued"] += 1
            logger.info("Queued job: %s (score=%.1f)", title[:60], ai_score)
            return json.dumps({"success": True, "id": result.get("id")})
        except Exception as exc:
            logger.warning("add_to_queue failed for %s: %s", upwork_url, exc)
            self._stats["errors"].append(f"add_to_queue failed: {exc}")
            return json.dumps({"success": False, "error": str(exc)})

    # ── Tool dispatch ──────────────────────────────────────────────────────

    async def _dispatch_tool(self, name: str, params: dict) -> str:
        """Route an Anthropic tool call to the appropriate async method."""
        if name == "get_search_queries":
            return await self._tool_get_search_queries()
        if name == "fetch_jobs_from_rss":
            return await self._tool_fetch_jobs_from_rss(
                url_params=params["url_params"],
                limit=params.get("limit", 20),
            )
        if name == "check_already_queued":
            return await self._tool_check_already_queued(params["upwork_url"])
        if name == "analyze_job":
            return await self._tool_analyze_job(
                title=params["title"],
                description=params["description"],
                upwork_url=params["upwork_url"],
                skills=params.get("skills"),
                budget_amount=params.get("budget_amount"),
            )
        if name == "add_to_queue":
            return await self._tool_add_to_queue(
                upwork_url=params["upwork_url"],
                title=params["title"],
                description=params["description"],
                skills=params.get("skills"),
                budget_amount=params.get("budget_amount"),
                budget_type=params.get("budget_type"),
                ai_score=params.get("ai_score", 0.0),
                ai_reasoning=params.get("ai_reasoning", ""),
                chips=params.get("chips"),
                source_query_id=params.get("source_query_id"),
            )
        return json.dumps({"error": f"Unknown tool: {name}"})

    # ── Tool definitions for Anthropic SDK ────────────────────────────────

    @staticmethod
    def _tool_definitions() -> list[dict]:
        return [
            {
                "name": "get_search_queries",
                "description": "Get the user's active Upwork search queries. Returns a JSON list of {id, query, url_params} objects.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "fetch_jobs_from_rss",
                "description": "Fetch recent Upwork job postings from the RSS feed using url_params from a search query.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url_params": {
                            "type": "string",
                            "description": "Raw URL query string for the Upwork RSS feed, e.g. 'q=python+fastapi&contractor_tier=2,3'",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of jobs to fetch (default 20, max 25)",
                            "default": 20,
                        },
                    },
                    "required": ["url_params"],
                },
            },
            {
                "name": "check_already_queued",
                "description": "Check if a job URL is already in the queue or jobs table. Returns {already_exists: bool}.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "upwork_url": {
                            "type": "string",
                            "description": "The full Upwork job URL",
                        },
                    },
                    "required": ["upwork_url"],
                },
            },
            {
                "name": "analyze_job",
                "description": "Score a job against the user's profile. Returns match_score (0-100), skill_matches, missing_skills, strengths, concerns.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string", "description": "Job description text (max 800 chars)"},
                        "upwork_url": {"type": "string"},
                        "skills": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Skills required for the job",
                        },
                        "budget_amount": {"type": "string", "description": "Budget as a string, e.g. '$500' or '$25/hr'"},
                    },
                    "required": ["title", "description", "upwork_url"],
                },
            },
            {
                "name": "add_to_queue",
                "description": "Add a qualifying job to the user's suggestion queue. Only call for jobs with score >= threshold.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "upwork_url": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "skills": {"type": "array", "items": {"type": "string"}},
                        "budget_amount": {"type": "string"},
                        "budget_type": {"type": "string", "enum": ["hourly", "fixed", None]},
                        "ai_score": {"type": "number", "description": "Score from analyze_job (0-100)"},
                        "ai_reasoning": {
                            "type": "string",
                            "description": "1-3 sentences explaining why this job fits the user's profile specifically.",
                        },
                        "chips": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "2-6 category chips: python, fastapi, react, typescript, sql, postgresql, azure, aws, ai, llm, saas, mvp, cto, advisory, fullstack, data, automation, backend, frontend",
                        },
                        "source_query_id": {
                            "type": "string",
                            "description": "ID of the search_query that produced this job",
                        },
                    },
                    "required": ["upwork_url", "title", "description", "ai_score", "ai_reasoning"],
                },
            },
        ]

    # ── Main run loop ──────────────────────────────────────────────────────

    async def run(
        self,
        user_id: str,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    ) -> DiscoveryResult:
        """Execute one full discovery run for the given user.

        Args:
            user_id:         The user's ID (used for logging; auth is via token).
            score_threshold: Minimum ai_score to add a job to the queue.

        Returns:
            DiscoveryResult with counters for what happened.
        """
        self._stats: dict = {
            "jobs_fetched": 0,
            "jobs_skipped_duplicate": 0,
            "jobs_scored": 0,
            "jobs_queued": 0,
            "errors": [],
        }

        system = SYSTEM_PROMPT.format(
            threshold=score_threshold,
            max_jobs=MAX_QUEUED_PER_RUN,
        )

        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Run a job discovery pass for the current user (threshold={score_threshold}). "
                    "Follow the workflow in the system prompt. Report a brief summary when done."
                ),
            }
        ]

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            self._http = http_client

            # Tool-use loop — max 25 turns to prevent runaway
            for turn in range(25):
                response = self._client.messages.create(
                    model=DISCOVERY_MODEL,
                    max_tokens=4096,
                    system=system,
                    tools=self._tool_definitions(),  # type: ignore[arg-type]
                    messages=messages,
                )

                # Append assistant response to history
                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn":
                    logger.info(
                        "Discovery run complete for user %s after %d turns: "
                        "fetched=%d skipped=%d scored=%d queued=%d",
                        user_id, turn + 1,
                        self._stats["jobs_fetched"],
                        self._stats["jobs_skipped_duplicate"],
                        self._stats["jobs_scored"],
                        self._stats["jobs_queued"],
                    )
                    break

                if response.stop_reason != "tool_use":
                    logger.warning("Unexpected stop_reason: %s", response.stop_reason)
                    break

                # Process all tool calls in this turn
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    try:
                        result_text = await self._dispatch_tool(block.name, block.input)
                    except Exception as exc:
                        logger.error("Tool %s raised: %s", block.name, exc)
                        result_text = json.dumps({"error": str(exc)})
                        self._stats["errors"].append(f"{block.name}: {exc}")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })

                messages.append({"role": "user", "content": tool_results})

                # Safety cap — stop if we've hit the per-run queue limit
                if self._stats["jobs_queued"] >= MAX_QUEUED_PER_RUN:
                    logger.info("Queue cap (%d) reached, stopping loop", MAX_QUEUED_PER_RUN)
                    break
            else:
                logger.warning("Discovery loop hit max turns (25) for user %s", user_id)

            self._http = None

        return DiscoveryResult(
            user_id=user_id,
            jobs_fetched=self._stats["jobs_fetched"],
            jobs_skipped_duplicate=self._stats["jobs_skipped_duplicate"],
            jobs_scored=self._stats["jobs_scored"],
            jobs_queued=self._stats["jobs_queued"],
            errors=self._stats["errors"],
        )
