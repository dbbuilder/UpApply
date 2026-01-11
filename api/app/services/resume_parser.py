"""Resume parsing service using OpenAI."""
import json
from typing import Dict, Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.embeddings import get_openai_client


RESUME_PARSE_PROMPT = """Analyze this resume and extract structured information.

Return a JSON object with the following structure:
{
    "full_name": "string or null",
    "professional_title": "string - their main job title/role",
    "bio": "string - a 2-3 sentence professional summary",
    "skills": [
        {"name": "skill name", "level": "beginner|intermediate|expert", "years": number or null}
    ],
    "work_history": [
        {
            "title": "job title",
            "company": "company name",
            "duration": "e.g., 2020-2023",
            "description": "brief description of role",
            "highlights": ["key achievement 1", "key achievement 2"]
        }
    ],
    "education": [
        {
            "degree": "degree name",
            "institution": "school name",
            "year": number or null,
            "relevant_courses": ["course 1", "course 2"] or null
        }
    ],
    "certifications": ["cert 1", "cert 2"],
    "memories": [
        {
            "title": "Brief title for this achievement/project",
            "content": "Detailed description of what was accomplished",
            "category": "project|achievement|skill_demo",
            "skills_demonstrated": ["skill1", "skill2"],
            "outcome": "The result or impact"
        }
    ]
}

Focus on:
1. Extract concrete achievements with metrics when available
2. Identify skills demonstrated in each role
3. Create "memories" from significant projects/achievements that can be used in cover letters
4. For skills, infer level based on experience duration and context
5. Make the bio engaging and specific, not generic

Resume text:
"""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def parse_resume(resume_text: str) -> Dict[str, Any]:
    """Parse resume text and extract structured information."""
    client = get_openai_client()

    response = await client.chat.completions.create(
        model=settings.default_model,
        messages=[
            {
                "role": "system",
                "content": "You are an expert resume parser. Extract structured information from resumes accurately. Always respond with valid JSON.",
            },
            {
                "role": "user",
                "content": RESUME_PARSE_PROMPT + resume_text,
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=4000,
        temperature=0.3,
    )

    result = json.loads(response.choices[0].message.content)
    return result
