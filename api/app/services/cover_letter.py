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
    name = profile.full_name or "the freelancer"
    title = profile.professional_title or "senior technical professional"

    parts = [
        f"You are ghostwriting an Upwork proposal for {name}, a {title}. "
        f"Write entirely in their voice — they are not a job applicant, they are a senior technical peer "
        f"evaluating whether this engagement is worth their time."
    ]

    if profile.bio:
        parts.append(f"\n\nBACKGROUND: {profile.bio[:400]}")

    if profile.career_goals:
        parts.append(f"\n\nWHAT THEY CARE ABOUT: {profile.career_goals}")

    if profile.communication_style:
        parts.append(f"\n\nSTYLE NOTES: {profile.communication_style}")

    if profile.unique_strengths:
        parts.append(f"\n\nCORE STRENGTHS: {', '.join(profile.unique_strengths)}")

    parts.append(f"""

VOICE:
- Peer-to-peer with founders and CTOs — never subordinate, never eager-to-please
- Opens with pattern recognition: one sentence showing you have seen this exact situation before
- Tells one specific concrete story from past work — real project name, real outcome
- Names specific failure modes and risk classes the client should worry about
- Weaves skills into narrative — never lists them as bullets
- Confident and direct, not arrogant or academic
- Ends as an equal: "if we work together, you can expect..." not "I look forward to hearing from you"

BANNED PHRASES (these signal generic AI writing — using any of these is a failure):
"I am well-equipped", "unique blend of skills", "align perfectly with your needs",
"I am excited to apply", "I look forward to hearing from you", "my skills directly translate",
"proven track record", "I am passionate about", "leverage my expertise",
"I believe I would be a great fit", "I am confident that", "strong background in",
"extensive experience in", "I would love the opportunity", "I am a perfect fit"

STRUCTURE — write these as flowing prose, do not label the sections:
1. Pattern recognition hook — one sentence identifying the core situation (e.g., "founder-built system hitting operational risk", "vibe-coded platform that needs guardrails")
2. One concrete past story — what you actually did in a near-identical situation: the specific problem, your specific action, the outcome. Use a real named project from their portfolio.
3. Failure modes you eliminate — name the specific risks this client faces and how you address them
4. 1-2 portfolio anchors — drop real product names with a sentence of context to establish range
5. Peer-level close — what working together will feel like, not a request for a callback

LENGTH: 300-450 words. No salutation. No signature. No placeholders.
No "Dear...", no "Subject:", no "Sincerely,", no name at the end.""")

    return "".join(parts)


def format_memories_for_prompt(memories: List[Dict]) -> str:
    """Format memories for inclusion in prompt."""
    if not memories:
        return "No specific relevant projects found."

    formatted = []
    for i, mem in enumerate(memories, 1):
        entry = f"{i}. {mem['title']}"
        if mem.get('content'):
            content = mem['content'][:600] + "..." if len(mem['content']) > 600 else mem['content']
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


def format_past_proposals(proposals: List[Dict]) -> str:
    """Format past proposals for inclusion in prompt as writing examples."""
    if not proposals:
        return ""

    formatted = []
    for i, prop in enumerate(proposals, 1):
        entry = f"Example {i}"
        if prop.get("job_title"):
            entry += f" - For: {prop['job_title']}"
        if prop.get("was_hired"):
            entry += " [SUCCESSFUL - Got Hired]"

        cover_letter = prop.get("cover_letter_text", "")
        # Truncate long cover letters but keep enough for style reference
        if len(cover_letter) > 600:
            cover_letter = cover_letter[:600] + "..."

        entry += f"\n{cover_letter}"

        if prop.get("job_skills"):
            skills = prop["job_skills"]
            if isinstance(skills, list):
                entry += f"\n(Skills: {', '.join(skills[:5])})"

        formatted.append(entry)

    return "\n\n".join(formatted)


def build_user_prompt(
    job_title: str,
    job_description: str,
    job_skills: List[str],
    budget: Optional[str],
    skill_matches: List[SkillMatch],
    missing_skills: List[str],
    relevant_memories: List[Dict],
    profile: UserProfile,
    past_proposals: Optional[List[Dict]] = None,
    inclusions: Optional[str] = None,
) -> str:
    """Build user prompt with job and match details."""
    parts = [
        "Write a proposal for this Upwork job in the voice described above.\n",
        f"JOB TITLE: {job_title}",
        f"\n\nJOB DESCRIPTION:\n{job_description[:2500]}",
    ]

    if job_skills:
        parts.append(f"\n\nSKILLS THEY NEED: {', '.join(job_skills)}")

    if budget:
        parts.append(f"\nBUDGET: {budget}")

    # Memories — expand truncation limit so there's real content to draw on
    if relevant_memories:
        parts.append(f"\n\nPORTFOLIO / RELEVANT EXPERIENCE (draw from these for the concrete story):\n{format_memories_for_prompt(relevant_memories)}")

    # Skill alignment as background context only — not to be listed
    skill_notes = format_skill_matches(skill_matches, missing_skills)
    if skill_notes and skill_notes != "No specific skill requirements identified.":
        parts.append(f"\n\nSKILL ALIGNMENT (background context — do NOT list these, weave into narrative):\n{skill_notes}")

    # Past successful proposals as voice calibration
    if past_proposals:
        past_proposals_text = format_past_proposals(past_proposals)
        if past_proposals_text:
            parts.append(
                f"\n\nPAST WINNING PROPOSALS (calibrate voice and structure from these — "
                f"especially the ones marked SUCCESSFUL):\n{past_proposals_text}"
            )

    # Skills to highlight
    if profile.skills_to_highlight:
        job_skills_lower = [s.lower() for s in job_skills]
        matching_highlights = [
            s for s in profile.skills_to_highlight
            if s.lower() in job_skills_lower or any(s.lower() in js for js in job_skills_lower)
        ]
        if matching_highlights:
            parts.append(f"\n\nEMPHASIZE THESE if they appear in the narrative: {', '.join(matching_highlights)}")

    if inclusions:
        formatted_inclusions = format_inclusions(inclusions)
        if formatted_inclusions:
            parts.append(f"\n\nREQUIRED INCLUSIONS:\n{formatted_inclusions}")

    parts.append(
        "\n\nNow write the proposal. Start with the pattern recognition hook — "
        "identify what situation this client is in and show you've been here before. "
        "Pick the most relevant portfolio story and tell it specifically. "
        "Name the failure modes. Anchor with portfolio products. Close as a peer."
    )

    return "".join(parts)


def format_inclusions(inclusions: str) -> str:
    """Parse inclusion instructions.

    Text in "quotes" should be included verbatim as exact phrases.
    Unquoted text is treated as concepts to weave in naturally.
    """
    if not inclusions or not inclusions.strip():
        return ""

    import re as _re
    exact: list[str] = []
    concepts: list[str] = []

    # Extract quoted phrases
    remaining = inclusions
    for match in _re.finditer(r'"([^"]+)"', inclusions):
        exact.append(match.group(1))
        remaining = remaining.replace(match.group(0), '')

    # Remaining unquoted text = concepts
    for part in remaining.split('\n'):
        part = part.strip().strip('-').strip('*').strip()
        if part:
            concepts.append(part)

    parts: list[str] = []
    if exact:
        parts.append("EXACT PHRASES TO INCLUDE (use these word-for-word somewhere in the letter):")
        for phrase in exact:
            parts.append(f'  - "{phrase}"')
    if concepts:
        parts.append("CONCEPTS TO WEAVE IN (incorporate these ideas naturally):")
        for concept in concepts:
            parts.append(f"  - {concept}")

    return "\n".join(parts)


def append_prototype_url(content: str, url: Optional[str]) -> str:
    """Append prototype URL sentence to cover letter if provided."""
    if not url or not url.strip():
        return content
    sentence = (
        "To demonstrate my excitement about this project and my capacity and velocity "
        f"to deliver, I created a prototype of this project at {url.strip()}. "
        "Please consider it as you review my application and how well I fit your needs."
    )
    return f"{content}\n\n{sentence}"


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
    past_proposals: Optional[List[Dict]] = None,
    inclusions: Optional[str] = None,
    prototype_url: Optional[str] = None,
) -> str:
    """Generate a personalized cover letter using OpenAI.

    Args:
        past_proposals: List of past proposals for similar jobs to use as style examples.
            Successful proposals (was_hired=True) are weighted more heavily.
    """
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
        past_proposals=past_proposals,
        inclusions=inclusions,
    )

    response = await client.chat.completions.create(
        model=model or settings.default_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1200,
        temperature=0.75,
    )

    raw_content = response.choices[0].message.content.strip()
    cleaned = clean_cover_letter(raw_content)
    with_prototype = append_prototype_url(cleaned, prototype_url)
    return append_closing(with_prototype, profile.preferred_closing)


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
