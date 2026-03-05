"""Screening answer endpoints with pgvector semantic search."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.embeddings import generate_embedding, get_openai_client
from app.models.user import User, UserProfile
from app.models.screening_answer import ScreeningAnswer
from app.schemas.screening_answer import (
    ScreeningAnswerCreate,
    ScreeningAnswerUpdate,
    ScreeningAnswerResponse,
    ScreeningAnswerSearchRequest,
    ScreeningAnswerSearchResult,
    ScreeningAnswerBulkCreate,
)


class ScreeningAnswerGenerateRequest(BaseModel):
    question: str
    job_title: Optional[str] = None
    job_description: Optional[str] = None
    job_skills: Optional[List[str]] = None


class ScreeningAnswerGenerateResponse(BaseModel):
    answer: str

router = APIRouter()


@router.post("", response_model=ScreeningAnswerResponse, status_code=status.HTTP_201_CREATED)
async def create_screening_answer(
    data: ScreeningAnswerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new screening answer with embeddings."""
    # Generate embeddings for question and answer
    question_embedding = await generate_embedding(data.question)
    answer_embedding = await generate_embedding(data.answer)

    # Convert job_skills list to comma-separated string if provided
    job_skills_str = ",".join(data.job_skills) if data.job_skills else None

    answer = ScreeningAnswer(
        user_id=current_user.id,
        job_id=data.job_id,
        application_id=data.application_id,
        question=data.question,
        answer=data.answer,
        question_type=data.question_type,
        job_title=data.job_title,
        job_skills=job_skills_str,
        question_embedding=question_embedding,
        answer_embedding=answer_embedding,
    )

    db.add(answer)
    await db.commit()
    await db.refresh(answer)

    return answer


@router.get("", response_model=List[ScreeningAnswerResponse])
async def list_screening_answers(
    job_id: Optional[str] = None,
    question_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's screening answers."""
    query = select(ScreeningAnswer).where(ScreeningAnswer.user_id == current_user.id)

    if job_id:
        query = query.where(ScreeningAnswer.job_id == job_id)
    if question_type:
        query = query.where(ScreeningAnswer.question_type == question_type)

    query = query.order_by(ScreeningAnswer.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    answers = result.scalars().all()

    return answers


@router.get("/{answer_id}", response_model=ScreeningAnswerResponse)
async def get_screening_answer(
    answer_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific screening answer."""
    result = await db.execute(
        select(ScreeningAnswer).where(
            ScreeningAnswer.id == answer_id, ScreeningAnswer.user_id == current_user.id
        )
    )
    answer = result.scalar_one_or_none()

    if not answer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Screening answer not found",
        )

    return answer


@router.put("/{answer_id}", response_model=ScreeningAnswerResponse)
async def update_screening_answer(
    answer_id: str,
    data: ScreeningAnswerUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a screening answer."""
    result = await db.execute(
        select(ScreeningAnswer).where(
            ScreeningAnswer.id == answer_id, ScreeningAnswer.user_id == current_user.id
        )
    )
    answer = result.scalar_one_or_none()

    if not answer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Screening answer not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Regenerate embedding if answer changed
    if "answer" in update_data:
        answer.answer_embedding = await generate_embedding(update_data["answer"])

    for field, value in update_data.items():
        setattr(answer, field, value)

    await db.commit()
    await db.refresh(answer)

    return answer


@router.delete("/{answer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_screening_answer(
    answer_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a screening answer."""
    result = await db.execute(
        select(ScreeningAnswer).where(
            ScreeningAnswer.id == answer_id, ScreeningAnswer.user_id == current_user.id
        )
    )
    answer = result.scalar_one_or_none()

    if not answer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Screening answer not found",
        )

    await db.delete(answer)
    await db.commit()


@router.post("/search", response_model=List[ScreeningAnswerSearchResult])
async def search_screening_answers(
    request: ScreeningAnswerSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for similar screening questions and their answers using semantic search."""
    # Generate embedding for the search question
    query_embedding = await generate_embedding(request.question)

    # Search by question similarity using pgvector
    sql = text("""
        SELECT
            id, user_id, job_id, application_id,
            question, answer, question_type,
            job_title, job_skills, was_successful, created_at,
            1 - (question_embedding <=> CAST(:embedding AS vector)) as similarity
        FROM screening_answers
        WHERE user_id = :user_id
        AND question_embedding IS NOT NULL
        ORDER BY question_embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    result = await db.execute(
        sql,
        {
            "embedding": str(query_embedding),
            "user_id": current_user.id,
            "limit": request.limit,
        },
    )

    rows = result.fetchall()

    search_results = []
    for row in rows:
        answer_response = ScreeningAnswerResponse(
            id=row.id,
            user_id=row.user_id,
            job_id=row.job_id,
            application_id=row.application_id,
            question=row.question,
            answer=row.answer,
            question_type=row.question_type,
            job_title=row.job_title,
            was_successful=row.was_successful,
            created_at=row.created_at,
        )

        search_results.append(
            ScreeningAnswerSearchResult(
                answer=answer_response,
                similarity=row.similarity,
            )
        )

    return search_results


@router.post("/generate", response_model=ScreeningAnswerGenerateResponse)
async def generate_screening_answer(
    request: ScreeningAnswerGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI-generate an answer for a screening question using profile and past answers."""
    # Load user profile
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    # Fetch past answers to similar questions via semantic search
    past_answers_text = ""
    try:
        q_embedding = await generate_embedding(request.question)
        sql = text("""
            SELECT question, answer, was_successful
            FROM screening_answers
            WHERE user_id = :user_id AND question_embedding IS NOT NULL
            ORDER BY question_embedding <=> CAST(:embedding AS vector)
            LIMIT 3
        """)
        rows = (await db.execute(sql, {"embedding": str(q_embedding), "user_id": current_user.id})).fetchall()
        if rows:
            parts = []
            for r in rows:
                tag = " (successful)" if r.was_successful else ""
                parts.append(f'Q: {r.question}\nA: {r.answer}{tag}')
            past_answers_text = "\n\n".join(parts)
    except Exception:
        pass

    # Build profile context
    profile_lines = []
    if profile:
        if profile.full_name:
            profile_lines.append(f"Name: {profile.full_name}")
        if profile.professional_title:
            profile_lines.append(f"Title: {profile.professional_title}")
        if profile.bio:
            profile_lines.append(f"Bio: {profile.bio[:300]}")
        if profile.skills:
            top_skills = [s.get("name", "") for s in (profile.skills or [])[:8]]
            profile_lines.append(f"Skills: {', '.join(top_skills)}")
        if profile.career_goals:
            profile_lines.append(f"Goals: {profile.career_goals[:200]}")

    profile_ctx = "\n".join(profile_lines) if profile_lines else "No profile available."
    job_ctx_parts = []
    if request.job_title:
        job_ctx_parts.append(f"Job: {request.job_title}")
    if request.job_skills:
        job_ctx_parts.append(f"Required skills: {', '.join(request.job_skills[:10])}")
    if request.job_description:
        job_ctx_parts.append(f"Description excerpt: {request.job_description[:400]}")
    job_ctx = "\n".join(job_ctx_parts) if job_ctx_parts else ""

    system_prompt = (
        "You are an expert freelancer writing concise, authentic screening question answers "
        "for Upwork job applications. Write in first person. Be specific, confident, and honest. "
        "2-5 sentences unless the question clearly requires more. No fluff, no filler phrases like "
        "'Great question!' or 'I'd be happy to'. Get straight to the answer."
    )

    user_prompt = f"""QUESTION: {request.question}

MY PROFILE:
{profile_ctx}

{f'JOB CONTEXT:{chr(10)}{job_ctx}{chr(10)}' if job_ctx else ''}
{f'SIMILAR PAST ANSWERS (for reference only — write fresh):{chr(10)}{past_answers_text}{chr(10)}' if past_answers_text else ''}
Write the answer now:"""

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.default_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=400,
        temperature=0.7,
    )
    answer = (response.choices[0].message.content or "").strip()
    return ScreeningAnswerGenerateResponse(answer=answer)


@router.post("/bulk", response_model=List[ScreeningAnswerResponse])
async def bulk_create_screening_answers(
    request: ScreeningAnswerBulkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk create screening answers (e.g., from a completed application)."""
    created_answers = []

    for data in request.answers:
        # Generate embeddings
        question_embedding = await generate_embedding(data.question)
        answer_embedding = await generate_embedding(data.answer)

        job_skills_str = ",".join(data.job_skills) if data.job_skills else None

        answer = ScreeningAnswer(
            user_id=current_user.id,
            job_id=data.job_id,
            application_id=data.application_id,
            question=data.question,
            answer=data.answer,
            question_type=data.question_type,
            job_title=data.job_title,
            job_skills=job_skills_str,
            question_embedding=question_embedding,
            answer_embedding=answer_embedding,
        )

        db.add(answer)
        created_answers.append(answer)

    await db.commit()

    for answer in created_answers:
        await db.refresh(answer)

    return created_answers
