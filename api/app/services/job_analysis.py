"""Job analysis and matching service."""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import generate_embedding
from app.models.user import UserProfile
from app.models.memory import Memory
from app.schemas.job import SkillMatch


@dataclass
class AnalysisResult:
    """Complete job analysis result."""
    match_score: float
    skill_matches: List[SkillMatch]
    missing_skills: List[str]
    strengths: List[str]
    concerns: List[str]
    deal_breaker_warnings: List[str]
    relevant_memories: List[Dict]
    recommendation: str


# Skill synonyms for fuzzy matching
SKILL_SYNONYMS = {
    "react": ["reactjs", "react.js", "react js"],
    "node": ["nodejs", "node.js", "node js"],
    "python": ["python3", "py"],
    "javascript": ["js", "ecmascript"],
    "typescript": ["ts"],
    "postgresql": ["postgres", "psql"],
    "mongodb": ["mongo"],
    "aws": ["amazon web services", "amazon aws"],
    "gcp": ["google cloud", "google cloud platform"],
    "azure": ["microsoft azure"],
    "docker": ["containerization"],
    "kubernetes": ["k8s"],
    "graphql": ["graph ql"],
    "rest": ["restful", "rest api"],
    "css": ["css3", "cascading style sheets"],
    "html": ["html5"],
    "sql": ["structured query language"],
    "nosql": ["no-sql"],
    "ci/cd": ["cicd", "continuous integration", "continuous deployment"],
    "agile": ["scrum", "kanban"],
    "git": ["github", "gitlab", "version control"],
}


def normalize_skill(skill: str) -> str:
    """Normalize a skill name for comparison."""
    return skill.lower().strip()


def skills_match(skill1: str, skill2: str) -> bool:
    """Check if two skills match (exact or synonym)."""
    s1 = normalize_skill(skill1)
    s2 = normalize_skill(skill2)

    if s1 == s2:
        return True

    # Check synonyms
    for primary, synonyms in SKILL_SYNONYMS.items():
        all_variants = [primary] + synonyms
        if s1 in all_variants and s2 in all_variants:
            return True

    return False


def find_related_skill(
    job_skill: str, user_skills: List[Dict]
) -> Optional[Tuple[Dict, str]]:
    """Find a related user skill for a job skill."""
    job_skill_lower = normalize_skill(job_skill)

    for user_skill in user_skills:
        if skills_match(job_skill, user_skill.get("name", "")):
            return user_skill, "exact"

    # Check for partial matches
    for user_skill in user_skills:
        user_skill_lower = normalize_skill(user_skill.get("name", ""))
        if job_skill_lower in user_skill_lower or user_skill_lower in job_skill_lower:
            return user_skill, "related"

    return None


async def analyze_skill_match(
    job_skills: List[str], user_profile: UserProfile
) -> Tuple[List[SkillMatch], List[str]]:
    """Analyze how well user skills match job requirements."""
    matches = []
    missing = []

    user_skills = user_profile.skills or []

    for job_skill in job_skills:
        result = find_related_skill(job_skill, user_skills)

        if result:
            user_skill, match_type = result
            matches.append(
                SkillMatch(
                    skill=job_skill,
                    match_type=match_type,
                    user_level=user_skill.get("level"),
                    relevance_score=1.0 if match_type == "exact" else 0.7,
                )
            )
        else:
            missing.append(job_skill)

    return matches, missing


async def find_relevant_memories_with_embedding(
    db: AsyncSession,
    user_id: str,
    query_embedding: List[float],
    limit: int = 5,
) -> List[Dict]:
    """Find memories relevant to the job using a pre-computed embedding."""
    sql = text("""
        SELECT
            id, title, content, category, skills_demonstrated,
            outcome, metrics, client_feedback,
            1 - (embedding <=> CAST(:embedding AS vector)) as similarity
        FROM memories
        WHERE user_id = :user_id
        AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    result = await db.execute(
        sql,
        {
            "embedding": str(query_embedding),
            "user_id": user_id,
            "limit": limit,
        },
    )

    memories = []
    for row in result.fetchall():
        if row.similarity > 0.3:  # Minimum relevance threshold
            memories.append({
                "id": row.id,
                "title": row.title,
                "content": row.content[:500] + "..." if len(row.content) > 500 else row.content,
                "category": row.category,
                "skills_demonstrated": row.skills_demonstrated,
                "outcome": row.outcome,
                "similarity": row.similarity,
            })

    return memories


async def find_relevant_memories(
    db: AsyncSession,
    user_id: str,
    job_description: str,
    job_skills: List[str],
    limit: int = 5,
) -> List[Dict]:
    """Find memories relevant to the job using semantic search."""
    # Create search text combining description and skills
    search_text = f"{job_description}\nRequired skills: {', '.join(job_skills)}"
    query_embedding = await generate_embedding(search_text)
    return await find_relevant_memories_with_embedding(
        db=db, user_id=user_id, query_embedding=query_embedding, limit=limit
    )


async def find_similar_wins(
    db: AsyncSession,
    user_id: str,
    query_embedding: List[float],
    limit: int = 3,
) -> List[Dict]:
    """Find past jobs where user was hired, ranked by similarity to current job."""
    sql = text("""
        SELECT j.title, j.description, j.skills_required,
               1 - (j.embedding <=> CAST(:embedding AS vector)) as similarity
        FROM jobs j
        JOIN applications a ON a.job_id = j.id
        WHERE j.user_id = :user_id
          AND a.user_id = :user_id
          AND a.status = 'hired'
          AND j.embedding IS NOT NULL
        ORDER BY j.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)
    result = await db.execute(sql, {
        "embedding": str(query_embedding),
        "user_id": user_id,
        "limit": limit,
    })
    wins = []
    for row in result.fetchall():
        wins.append({
            "title": row.title,
            "description": (row.description or "")[:300],
            "skills": row.skills_required or [],
            "similarity": float(row.similarity),
        })
    return wins


async def find_similar_highly_rated(
    db: AsyncSession,
    user_id: str,
    query_embedding: List[float],
    limit: int = 3,
) -> List[Dict]:
    """Find jobs the user rated 4-5 stars — strong positive signal for scoring calibration."""
    from app.models.job_review import JobReview
    result = await db.execute(
        select(JobReview).where(
            JobReview.user_id == user_id,
            JobReview.user_rating >= 4,
        ).order_by(JobReview.created_at.desc()).limit(limit * 3)
    )
    reviews = result.scalars().all()
    return [
        {
            "job_title": r.job_title,
            "user_comment": r.user_comment or "",
            "ai_score": r.ai_score,
            "chips": r.chips or [],
        }
        for r in reviews[:limit]
    ]


async def score_job_with_llm(
    job_title: str,
    job_description: str,
    profile: UserProfile,
    similar_wins: List[Dict],
    highly_rated: List[Dict] = [],
) -> Optional[float]:
    """Use gpt-4o-mini to score 0-100 with win rubric. Returns None on failure."""
    import json
    from openai import AsyncOpenAI
    from app.core.config import settings

    if not settings.openai_api_key:
        return None

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    skills_str = ", ".join([
        s.get("name", "") for s in (profile.skills or [])[:25] if s.get("name")
    ])

    if similar_wins:
        win_context = "\n\nPAST JOBS THIS FREELANCER WAS HIRED FOR (calibration examples):\n"
        for i, win in enumerate(similar_wins, 1):
            sim_pct = int(win["similarity"] * 100)
            win_context += f"{i}. \"{win['title']}\" ({sim_pct}% similar to current job)\n"
            if win["description"]:
                win_context += f"   {win['description'][:200]}\n"
    else:
        win_context = "\n\n(No past hired jobs recorded yet — score based on profile fit only.)\n"

    if highly_rated:
        highly_rated_context = "\nJobs this freelancer rated 4-5 stars (strong personal fit):\n"
        for r in highly_rated[:3]:
            note = r.get("user_comment", "")
            highly_rated_context += f'  - "{r["job_title"]}"' + (f' — note: "{note}"' if note else "") + "\n"
    else:
        highly_rated_context = ""

    bio_snippet = (profile.bio or "")[:400]
    goals_snippet = (profile.career_goals or "")[:200]
    desc_snippet = job_description[:1500]

    prompt = f"""You are scoring a freelance Upwork job for this consultant. Be discriminating — most jobs should score 40–70, exceptional fits 85+, poor fits below 35.

CONSULTANT:
Skills: {skills_str}
Bio: {bio_snippet}
Goals: {goals_snippet}
{win_context}{highly_rated_context}
JOB TO SCORE:
Title: {job_title}
Description: {desc_snippet}

RUBRIC:
85–100 = Near-perfect match; closely resembles past wins; very high win probability
65–84  = Strong match; competitive candidate; likely to win
45–64  = Moderate fit; relevant skills but some gaps
25–44  = Weak fit; significant skill or domain mismatch
0–24   = Poor fit; not worth applying

Respond with JSON only (no markdown): {{"score": <integer 0-100>, "reason": "<one sentence max 120 chars>"}}"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=80,
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        score = float(data.get("score", 0))
        return min(max(score, 0), 100)
    except Exception:
        return None


def check_deal_breakers(
    job_description: str,
    job_skills: List[str],
    budget_amount: Optional[str],
    budget_min: Optional[float],
    client_info: Optional[Dict],
    profile: UserProfile,
) -> List[str]:
    """Check for deal breaker warnings."""
    warnings = []
    description_lower = job_description.lower()

    # Check avoided keywords
    if profile.avoid_keywords:
        for keyword in profile.avoid_keywords:
            if keyword.lower() in description_lower:
                warnings.append(f"Contains avoided keyword: '{keyword}'")

    # Check minimum budget
    if profile.minimum_budget and budget_min:
        if budget_min < float(profile.minimum_budget):
            warnings.append(
                f"Budget ${budget_min} is below your minimum ${profile.minimum_budget}"
            )

    # Check minimum hourly rate
    if profile.minimum_hourly_rate and budget_amount:
        if "/hr" in budget_amount.lower() or "hourly" in budget_amount.lower():
            # Try to extract rate
            import re
            rate_match = re.search(r"\$(\d+)", budget_amount)
            if rate_match:
                rate = float(rate_match.group(1))
                if rate < float(profile.minimum_hourly_rate):
                    warnings.append(
                        f"Hourly rate ${rate} is below your minimum ${profile.minimum_hourly_rate}"
                    )

    # Check red flag patterns
    if profile.red_flag_patterns:
        for pattern in profile.red_flag_patterns:
            if pattern.lower() in description_lower:
                warnings.append(f"Red flag detected: '{pattern}'")

    # Client red flags
    if client_info:
        hire_rate = client_info.get("hire_rate", "")
        if hire_rate and "0%" in hire_rate:
            warnings.append("Client has 0% hire rate")

        total_spent = client_info.get("total_spent", "")
        if total_spent and "$0" in total_spent:
            warnings.append("Client has never hired on Upwork")

    return warnings


def generate_strengths_and_concerns(
    skill_matches: List[SkillMatch],
    missing_skills: List[str],
    relevant_memories: List[Dict],
    profile: UserProfile,
    budget_amount: Optional[str],
) -> Tuple[List[str], List[str]]:
    """Generate strengths and concerns for the job match."""
    strengths = []
    concerns = []

    # Skill-based strengths
    expert_matches = [m for m in skill_matches if m.user_level == "expert"]
    if len(expert_matches) >= 2:
        skills = ", ".join([m.skill for m in expert_matches[:3]])
        strengths.append(f"Expert-level skills in: {skills}")
    elif skill_matches:
        match_rate = len(skill_matches) / (len(skill_matches) + len(missing_skills))
        if match_rate >= 0.7:
            strengths.append(f"Strong skill match ({int(match_rate * 100)}% of required skills)")

    # Memory-based strengths
    if relevant_memories:
        top_memory = relevant_memories[0]
        if top_memory.get("similarity", 0) > 0.6:
            strengths.append(f"Highly relevant experience: {top_memory['title']}")
        elif len(relevant_memories) >= 3:
            strengths.append(f"{len(relevant_memories)} relevant projects in portfolio")

    # Profile-based strengths
    if profile.unique_strengths:
        strengths.append(f"Unique strength: {profile.unique_strengths[0]}")

    # Concerns
    if missing_skills:
        if len(missing_skills) <= 2:
            concerns.append(f"Missing skills: {', '.join(missing_skills)}")
        else:
            concerns.append(f"Missing {len(missing_skills)} required skills")

    # Rate concerns
    if profile.hourly_rate_preferred and budget_amount:
        if "/hr" in budget_amount.lower():
            import re
            rate_match = re.search(r"\$(\d+)", budget_amount)
            if rate_match:
                rate = float(rate_match.group(1))
                if rate < float(profile.hourly_rate_preferred) * 0.8:
                    concerns.append(
                        f"Rate ${rate}/hr is below your preferred ${profile.hourly_rate_preferred}/hr"
                    )

    return strengths, concerns


def calculate_match_score(
    skill_matches: List[SkillMatch],
    missing_skills: List[str],
    relevant_memories: List[Dict],
    deal_breakers: List[str],
    profile: UserProfile,
) -> float:
    """Calculate overall match score (0-100)."""
    if not skill_matches and not missing_skills:
        # No skills specified in job
        base_score = 50
    else:
        # Skills weight: 40%
        total_skills = len(skill_matches) + len(missing_skills)
        skill_score = (len(skill_matches) / total_skills * 100) if total_skills > 0 else 50

        # Expert bonus
        expert_count = sum(1 for m in skill_matches if m.user_level == "expert")
        skill_bonus = min(expert_count * 5, 15)

        base_score = skill_score * 0.4 + skill_bonus

    # Memory relevance weight: 30%
    if relevant_memories:
        avg_relevance = sum(m.get("similarity", 0) for m in relevant_memories) / len(relevant_memories)
        memory_score = avg_relevance * 100 * 0.3
    else:
        memory_score = 15  # Neutral

    # Profile completeness weight: 15%
    profile_fields = [
        profile.bio,
        profile.skills,
        profile.work_history,
        profile.unique_strengths,
    ]
    profile_completeness = sum(1 for f in profile_fields if f) / len(profile_fields)
    profile_score = profile_completeness * 100 * 0.15

    # Preference alignment weight: 15%
    preference_score = 15  # Base score, could be enhanced with more checks

    total = base_score + memory_score + profile_score + preference_score

    # Deal breaker penalty
    if deal_breakers:
        total = max(total - len(deal_breakers) * 10, 20)

    return min(max(round(total, 1), 0), 100)


def generate_recommendation(
    match_score: float, deal_breakers: List[str], concerns: List[str]
) -> str:
    """Generate overall recommendation."""
    if deal_breakers:
        return f"Review carefully - {len(deal_breakers)} potential issue(s) detected"

    if match_score >= 80:
        return "Excellent match - highly recommended to apply"
    elif match_score >= 65:
        return "Good match - consider applying"
    elif match_score >= 50:
        return "Moderate match - apply if interested in the project"
    else:
        return "Lower match - may require additional skills demonstration"


async def run_full_analysis(
    db: AsyncSession,
    user_id: str,
    profile: UserProfile,
    job_description: str,
    job_skills: List[str],
    budget_amount: Optional[str] = None,
    budget_min: Optional[float] = None,
    client_info: Optional[Dict] = None,
) -> AnalysisResult:
    """Run complete job analysis pipeline and return consolidated result."""
    skill_matches, missing_skills = await analyze_skill_match(job_skills, profile)

    # Generate embedding once and reuse for both memories and win lookup
    search_text = f"{job_description}\nRequired skills: {', '.join(job_skills)}"
    query_embedding = await generate_embedding(search_text)

    relevant_memories = await find_relevant_memories_with_embedding(
        db=db,
        user_id=user_id,
        query_embedding=query_embedding,
        limit=5,
    )

    similar_wins = await find_similar_wins(
        db=db,
        user_id=user_id,
        query_embedding=query_embedding,
        limit=3,
    )

    highly_rated = await find_similar_highly_rated(
        db=db,
        user_id=user_id,
        query_embedding=query_embedding,
        limit=3,
    )

    deal_breakers = check_deal_breakers(
        job_description=job_description,
        job_skills=job_skills,
        budget_amount=budget_amount,
        budget_min=budget_min,
        client_info=client_info,
        profile=profile,
    )

    strengths, concerns = generate_strengths_and_concerns(
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        relevant_memories=relevant_memories,
        profile=profile,
        budget_amount=budget_amount,
    )

    rule_score = calculate_match_score(
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        relevant_memories=relevant_memories,
        deal_breakers=deal_breakers,
        profile=profile,
    )

    # Use LLM scoring blended with rule-based (70/30) when available
    job_title = job_description[:80]
    llm_score = await score_job_with_llm(
        job_title=job_title,
        job_description=job_description,
        profile=profile,
        similar_wins=similar_wins,
        highly_rated=highly_rated,
    )

    if llm_score is not None:
        match_score = round(0.7 * llm_score + 0.3 * rule_score, 1)
    else:
        match_score = rule_score

    recommendation = generate_recommendation(match_score, deal_breakers, concerns)

    return AnalysisResult(
        match_score=match_score,
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        strengths=strengths,
        concerns=concerns,
        deal_breaker_warnings=deal_breakers,
        relevant_memories=relevant_memories,
        recommendation=recommendation,
    )


async def find_relevant_proposals(
    db: AsyncSession,
    user_id: str,
    job_description: str,
    job_skills: List[str],
    limit: int = 3,
    successful_only: bool = False,
) -> List[Dict]:
    """Find past proposals relevant to the job using semantic search.

    Returns proposals that were written for similar jobs, prioritizing
    successful proposals (those that led to being hired).
    """
    # Create search text combining description and skills
    search_text = f"{job_description}\nRequired skills: {', '.join(job_skills)}"
    query_embedding = await generate_embedding(search_text)

    # Vector similarity search on past proposals
    # Optionally filter to only successful proposals
    sql = text("""
        SELECT
            id, job_title, cover_letter_text, job_skills,
            bid_amount, bid_type, was_hired, status,
            1 - (embedding <=> CAST(:embedding AS vector)) as similarity
        FROM proposals
        WHERE user_id = :user_id
        AND embedding IS NOT NULL
        """ + ("AND was_hired = true" if successful_only else "") + """
        ORDER BY
            CASE WHEN was_hired = true THEN 0 ELSE 1 END,
            embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    result = await db.execute(
        sql,
        {
            "embedding": str(query_embedding),
            "user_id": user_id,
            "limit": limit,
        },
    )

    proposals = []
    for row in result.fetchall():
        if row.similarity > 0.25:  # Lower threshold than memories since proposals are rarer
            proposals.append({
                "id": row.id,
                "job_title": row.job_title,
                "cover_letter_text": row.cover_letter_text,
                "job_skills": row.job_skills,
                "bid_amount": float(row.bid_amount) if row.bid_amount else None,
                "bid_type": row.bid_type,
                "was_hired": row.was_hired,
                "status": row.status,
                "similarity": row.similarity,
            })

    return proposals
