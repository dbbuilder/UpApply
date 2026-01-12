"""Screening answer endpoints with pgvector semantic search."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.embeddings import generate_embedding
from app.models.user import User
from app.models.screening_answer import ScreeningAnswer
from app.schemas.screening_answer import (
    ScreeningAnswerCreate,
    ScreeningAnswerUpdate,
    ScreeningAnswerResponse,
    ScreeningAnswerSearchRequest,
    ScreeningAnswerSearchResult,
    ScreeningAnswerBulkCreate,
)

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
