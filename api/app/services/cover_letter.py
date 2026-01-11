"""Cover letter generation service using OpenAI."""
import json
from typing import Dict, Any, List, Optional

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.embeddings import get_openai_client
from app.models.user import UserProfile
from app.schemas.job import SkillMatch


def build_system_prompt(profile: UserProfile) -> str:
    """Build system prompt from user profile."""
    prompt_parts = [
        f"You are writing a cover letter for {profile.full_name or 'a freelancer'}, "
        f"a {profile.professional_title or 'professional'}."
    ]

    if profile.career_goals:
        prompt_parts.append(f"\nTHEIR GOALS: {profile.career_goals}")

    if profile.ideal_project_description:
        prompt_parts.append(f"\nIDEAL PROJECT: {profile.ideal_project_description}")

    if profile.unique_strengths:
        prompt_parts.append(f"\nUNIQUE STRENGTHS: {', '.join(profile.unique_strengths)}")

    tone = profile.tone_preference or "professional"
    prompt_parts.append(f"\nTONE: {tone}")

    if profile.communication_style:
        prompt_parts.append(f"\nSTYLE NOTES: {profile.communication_style}")

    prompt_parts.append("""

GUIDELINES:
- Lead with understanding their specific problem
- Highlight skills they WANT to use based on the job match
- Reference specific relevant experiences from provided memories
- Match the specified tone preference
- Keep under 300 words
- End with clear call to action
- NO generic phrases like "I am excited to apply" or "I look forward to hearing from you"
- NO placeholders like [Your Name] or [Company]
- Be specific about how past experience applies to THIS job
- Focus on value you can provide, not just qualifications""")

    return "".join(prompt_parts)


def format_memories_for_prompt(memories: List[Dict]) -> str:
    """Format memories for inclusion in prompt."""
    if not memories:
        return "No specific relevant projects found."

    formatted = []
    for i, mem in enumerate(memories, 1):
        entry = f"{i}. {mem['title']}"
        if mem.get('content'):
            # Truncate if too long
            content = mem['content'][:300] + "..." if len(mem['content']) > 300 else mem['content']
            entry += f"\n   {content}"
        if mem.get('outcome'):
            entry += f"\n   Outcome: {mem['outcome']}"
        if mem.get('skills_demonstrated'):
            skills = mem['skills_demonstrated']
            if isinstance(skills, list):
                entry += f"\n   Skills: {', '.join(skills)}"
        formatted.append(entry)

    return "\n\n".join(formatted)


def format_skill_matches(
    matches: List[SkillMatch], missing: List[str]
) -> str:
    """Format skill matching information for prompt."""
    parts = []

    if matches:
        exact = [m.skill for m in matches if m.match_type == "exact"]
        related = [m.skill for m in matches if m.match_type == "related"]

        if exact:
            parts.append(f"Exact matches: {', '.join(exact)}")
        if related:
            parts.append(f"Related skills: {', '.join(related)}")

    if missing:
        parts.append(f"Skills to address: {', '.join(missing)}")

    return "\n".join(parts) if parts else "No specific skill requirements identified."


def build_user_prompt(
    job_title: str,
    job_description: str,
    job_skills: List[str],
    budget: Optional[str],
    skill_matches: List[SkillMatch],
    missing_skills: List[str],
    relevant_memories: List[Dict],
    profile: UserProfile,
) -> str:
    """Build user prompt with job and match details."""
    parts = [
        f"JOB: {job_title}",
        f"\nDESCRIPTION:\n{job_description[:2000]}",  # Limit description length
    ]

    if job_skills:
        parts.append(f"\nREQUIRED SKILLS: {', '.join(job_skills)}")

    if budget:
        parts.append(f"\nBUDGET: {budget}")

    parts.append(f"\n\nRELEVANT EXPERIENCE FROM MY PORTFOLIO:\n{format_memories_for_prompt(relevant_memories)}")

    parts.append(f"\n\nSKILL ALIGNMENT:\n{format_skill_matches(skill_matches, missing_skills)}")

    # Add skills to highlight if they match job requirements
    if profile.skills_to_highlight:
        matching_highlights = []
        job_skills_lower = [s.lower() for s in job_skills]
        for skill in profile.skills_to_highlight:
            if skill.lower() in job_skills_lower or any(
                skill.lower() in js for js in job_skills_lower
            ):
                matching_highlights.append(skill)
        if matching_highlights:
            parts.append(f"\n\nUSER'S PREFERRED FOCUS (emphasize these if relevant):\n{', '.join(matching_highlights)}")

    parts.append("\n\nGenerate a personalized, compelling cover letter for this job.")

    return "".join(parts)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def generate_cover_letter(
    job_title: str,
    job_description: str,
    job_skills: List[str],
    budget: Optional[str],
    skill_matches: List[SkillMatch],
    missing_skills: List[str],
    relevant_memories: List[Dict],
    profile: UserProfile,
    model: Optional[str] = None,
) -> str:
    """Generate a personalized cover letter using OpenAI."""
    client = get_openai_client()

    system_prompt = build_system_prompt(profile)
    user_prompt = build_user_prompt(
        job_title=job_title,
        job_description=job_description,
        job_skills=job_skills,
        budget=budget,
        skill_matches=skill_matches,
        missing_skills=missing_skills,
        relevant_memories=relevant_memories,
        profile=profile,
    )

    response = await client.chat.completions.create(
        model=model or settings.default_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1000,
        temperature=0.7,
    )

    return response.choices[0].message.content.strip()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def regenerate_cover_letter(
    original_letter: str,
    feedback: str,
    job_title: str,
    job_description: str,
    profile: UserProfile,
    model: Optional[str] = None,
) -> str:
    """Regenerate cover letter with user feedback."""
    client = get_openai_client()

    system_prompt = build_system_prompt(profile)
    user_prompt = f"""Previous cover letter:
{original_letter}

User feedback for improvement:
{feedback}

Job: {job_title}

Please revise the cover letter based on this feedback while maintaining personalization for the job."""

    response = await client.chat.completions.create(
        model=model or settings.default_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1000,
        temperature=0.7,
    )

    return response.choices[0].message.content.strip()
