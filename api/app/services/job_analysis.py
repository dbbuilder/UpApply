"""Job analysis and matching service."""
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import generate_embedding
from app.models.user import UserProfile
from app.models.memory import Memory
from app.schemas.job import SkillMatch


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

    # Vector similarity search
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
