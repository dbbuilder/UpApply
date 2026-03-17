"""Upwork profile optimization service using Claude."""
import json
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.models.user import UserProfile
from app.schemas.profile import (
    May2026Item,
    ProfileDimension,
    ProfileOptimizeResponse,
    ProfileRecommendation,
)


def _get_anthropic_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _build_optimization_prompt(profile: UserProfile) -> str:
    """Build a comprehensive prompt encoding all Upwork profile best practices."""

    # Gather profile signals
    title = profile.professional_title or ""
    bio = profile.bio or ""
    hourly_rate = float(profile.hourly_rate_preferred or profile.hourly_rate_min or 0)
    hours_available = profile.hours_per_week_available or 0
    accepting_work = profile.currently_accepting_work

    skills: List[Dict[str, Any]] = []
    if profile.skills:
        skills = profile.skills if isinstance(profile.skills, list) else []
    skill_names = [s.get("name", "") if isinstance(s, dict) else str(s) for s in skills]

    anchors: dict = profile.proposal_anchors or {}
    specialization_count = len([k for k in anchors if k not in ("always_include",)])

    portfolio_links: List[str] = profile.portfolio_links or []

    profile_block = f"""
FREELANCER PROFILE DATA:
- Professional Title: {title or '(not set)'}
- Title Length: {len(title)} chars (hard limit: 50)
- Bio/Overview: {len(bio)} chars (optimal: 1500–2500 words ≈ 8000–13500 chars)
- Bio first 300 chars: {bio[:300] or '(not set)'}
- Hourly Rate Preferred: ${hourly_rate:.0f}/hr
- Hours Available/Week: {hours_available}
- Currently Accepting Work: {accepting_work}
- Skills List: {', '.join(skill_names) if skill_names else '(none)'}
- Skill Count: {len(skill_names)} (optimal: 10–15)
- Portfolio Links Count: {len(portfolio_links)}
- Specialization Areas Configured: {specialization_count} (from proposal_anchors)
""".strip()

    return f"""You are an expert Upwork profile consultant. Analyze this freelancer's profile data and return a structured JSON optimization report.

{profile_block}

EVALUATION CRITERIA — apply all of the following:

TITLE (dimension name: "Title"):
- Hard 50-character limit. Violating this is critical.
- Formula: [Primary Skill] | [Niche] | [Outcome]. Lead with the most-searched keyword.
- Avoid vague titles like "Experienced Developer" — be specific.
- Score 0–100 based on keyword clarity, niche specificity, outcome focus, and char count.

OVERVIEW HOOK (dimension name: "Overview Hook"):
- First 200–250 chars are all clients see before "Read More". This is the most valuable real estate.
- Must answer: who you help + what outcome + one proof point.
- No AI filler ("I am passionate about...", "I have extensive experience...").
- Score based on specificity, proof point, and hook strength.

OVERVIEW LENGTH (dimension name: "Overview Length"):
- Full overview: 1500–2500 words (8000–13500 chars). Short profiles rank lower algorithmically.
- Score based on actual char count vs optimal range.

SKILLS (dimension name: "Skills"):
- Optimal: 10–15 skills. Fewer than 10 = missing search traffic. More than 15 = incoherence penalty.
- Skills must be consistent with title and overview (algorithm detects mismatch).
- Should be ordered by relevance to primary niche.
- Score based on count, coherence signal, and relevance to title.

PORTFOLIO (dimension name: "Portfolio"):
- Freelancers with portfolio are hired 9x more. Need 5–8 strong pieces.
- Infer from portfolio_links count. Fewer than 3 is critical.
- Score based on portfolio_links count (0=0, 1-2=30, 3-4=60, 5-8=90–100).

AVAILABILITY (dimension name: "Availability"):
- "Available Now" badge → 50% more invites, positive ranking signal.
- Currently accepting work AND hours > 0 → full score.
- Score based on currently_accepting_work flag and hours_per_week_available.

RATE POSITIONING (dimension name: "Rate Positioning"):
- Rate must reflect positioning. Senior/CTO rate: $125–$200+/hr. Mid-market: $75–$125/hr. Entry: <$75/hr.
- Evaluate whether the rate matches the apparent seniority implied by the title and skills.
- Score based on alignment of rate to apparent positioning.

PROFILE COMPLETENESS (dimension name: "Profile Completeness"):
- All sections filled drives algorithmic visibility. Check title, bio, skills, portfolio.
- Score: 100 if all critical sections filled, deduct 15–25 per missing section.

OVERALL SCORE: Weighted average — Overview Hook and Title have 2x weight. Others 1x.

STATUS RULES:
- score >= 75: "good"
- score 50–74: "warning"
- score < 50: "critical"

PRIORITY RULES for recommendations:
- "critical": score < 50 or violates a hard rule (e.g. title over 50 chars)
- "high": score 50–64
- "medium": score 65–74
- "low": score >= 75 but still improvable

MAY 28 2026 DEADLINE — Specialized Profiles are being discontinued on May 28, 2026.
Generate a checklist with these exact items (mark done=true only if the evidence clearly supports it):
1. "Audit specialized profile titles/overviews before May 28" — done if specialization_count > 0 AND title is set
2. "Manually merge best specialized content into main profile" — done if bio length > 5000 (suggests merged content)
3. "Confirm portfolio pieces transfer (they do auto-transfer)" — done=true always (this is factual, no action needed)
4. "Remove or archive specialized profiles after merging" — done if specialization_count == 0
5. "Verify main profile title/overview post-merge" — done if title length >= 30 AND bio length >= 3000

REWRITE SUGGESTIONS:
- suggested_title: Rewrite the title following the formula. Keep <= 50 chars. If title is already strong, still provide a polished version.
- suggested_overview_hook: Write a 200–250 char hook following: [who you help] + [outcome] + [one proof point]. Use the profile data to make it specific.
- suggested_skills: Suggest an ordered list of 12 skills based on the title and existing skills. Remove low-signal or duplicate skills.

Return ONLY valid JSON matching this exact schema (no markdown, no code fences):
{{
  "overall_score": <int 0-100>,
  "dimensions": [
    {{
      "name": "<string>",
      "score": <int 0-100>,
      "status": "<good|warning|critical>",
      "summary": "<one sentence>",
      "detail": "<2-3 sentences with specific actionable context>"
    }}
  ],
  "recommendations": [
    {{
      "priority": "<critical|high|medium|low>",
      "dimension": "<dimension name>",
      "title": "<short action title>",
      "problem": "<what is wrong>",
      "action": "<exact step to fix it>"
    }}
  ],
  "suggested_title": "<string, max 50 chars>",
  "suggested_overview_hook": "<string, 200-250 chars>",
  "suggested_skills": ["skill1", "skill2", ...],
  "may_2026_checklist": [
    {{"item": "<string>", "done": <bool>, "note": "<short context string>"}}
  ]
}}

Only include recommendations for dimensions that score below 85. Sort recommendations: critical first, then high, then medium, then low.
"""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def optimize_profile(profile: UserProfile) -> ProfileOptimizeResponse:
    """Run AI-powered Upwork profile optimization analysis.

    Returns a ProfileOptimizeResponse with scores, recommendations, and rewrite
    suggestions. The result is meant to be cached in user_profiles.optimization_result.
    """
    client = _get_anthropic_client()
    prompt = _build_optimization_prompt(profile)

    response = await client.messages.create(
        model=settings.cover_letter_model,
        system=(
            "You are an expert Upwork profile consultant. "
            "You respond ONLY with valid JSON — no markdown, no explanation, no code fences. "
            "Every field in the schema must be present."
        ),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        temperature=0.2,
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if the model included them anyway
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3].strip()

    data = json.loads(raw)

    dimensions = [ProfileDimension(**d) for d in data.get("dimensions", [])]
    recommendations = [ProfileRecommendation(**r) for r in data.get("recommendations", [])]
    checklist = [May2026Item(**item) for item in data.get("may_2026_checklist", [])]

    return ProfileOptimizeResponse(
        overall_score=int(data.get("overall_score", 0)),
        dimensions=dimensions,
        recommendations=recommendations,
        suggested_title=data.get("suggested_title"),
        suggested_overview_hook=data.get("suggested_overview_hook"),
        suggested_skills=data.get("suggested_skills"),
        may_2026_checklist=checklist,
        cached=False,
        cached_at=None,
    )
