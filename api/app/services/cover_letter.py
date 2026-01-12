"""Cover letter generation service using OpenAI."""
import re
from typing import Dict, Any, List, Optional

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.embeddings import get_openai_client
from app.models.user import UserProfile
from app.schemas.job import SkillMatch


def clean_cover_letter(content: str) -> str:
    """Remove unwanted elements from generated cover letter."""
    lines = content.strip().split('\n')
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        # Skip Subject: lines
        if stripped.lower().startswith('subject:'):
            continue

        # Skip Dear... lines
        if stripped.lower().startswith('dear '):
            continue

        # Skip common signature lines
        if stripped.lower() in ['sincerely,', 'best regards,', 'regards,', 'best,', 'thank you,', 'thanks,', 'warm regards,']:
            continue

        # Skip lines that are just a name (likely signature)
        if len(stripped.split()) <= 3 and stripped and not any(c in stripped for c in '.!?:,'):
            # Check if it looks like a name at the end
            if cleaned_lines and cleaned_lines[-1].strip().lower() in ['sincerely,', 'best regards,', 'regards,', 'best,']:
                continue

        cleaned_lines.append(line)

    result = '\n'.join(cleaned_lines).strip()

    # Remove any bracketed placeholders like [Your Name], [Company], etc.
    result = re.sub(r'\[[\w\s\']+\]', '', result)

    # Clean up any double spaces or extra newlines created
    result = re.sub(r'  +', ' ', result)
    result = re.sub(r'\n{3,}', '\n\n', result)

    # Remove trailing signature-like content
    # Pattern: ends with "Sincerely," or similar followed by optional name
    result = re.sub(r'\n+(Sincerely|Best regards|Regards|Best|Thank you|Thanks|Warm regards),?\s*\n*[\w\s]*$', '', result, flags=re.IGNORECASE)

    return result.strip()


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
- NO placeholders like [Your Name], [Company], [Hiring Manager], etc.
- NO "Dear..." salutation line - start directly with the content
- NO "Subject:" line
- NO signature block at the end (no "Sincerely," or name)
- Be specific about how past experience applies to THIS job
- Focus on value you can provide, not just qualifications
- Start the letter immediately with a compelling opening sentence""")

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


def append_closing(content: str, closing: Optional[str]) -> str:
    """Append user's preferred closing to cover letter if provided."""
    if not closing:
        return content
    return f"{content}\n\n{closing}"


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

    raw_content = response.choices[0].message.content.strip()
    cleaned = clean_cover_letter(raw_content)
    return append_closing(cleaned, profile.preferred_closing)


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

Please revise the cover letter based on this feedback while maintaining personalization for the job. Remember: NO salutation line, NO signature, NO placeholders."""

    response = await client.chat.completions.create(
        model=model or settings.default_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1000,
        temperature=0.7,
    )

    raw_content = response.choices[0].message.content.strip()
    cleaned = clean_cover_letter(raw_content)
    return append_closing(cleaned, profile.preferred_closing)
