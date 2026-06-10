"""Work log endpoints — time and task capture against active contracts."""
import base64
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.embeddings import get_openai_client
from app.models.user import User
from app.models.work_log import WorkLog
from app.schemas.work_log import (
    WorkLogCreate,
    WorkLogUpdate,
    WorkLogResponse,
    WorkLogListResponse,
    ExtractImageRequest,
    ExtractImageResponse,
)

router = APIRouter()


@router.post("", response_model=WorkLogResponse, status_code=status.HTTP_201_CREATED)
async def create_work_log(
    data: WorkLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new work log entry."""
    log = WorkLog(
        user_id=current_user.id,
        job_id=data.job_id,
        contract_title=data.contract_title,
        upwork_contract_id=data.upwork_contract_id,
        task_description=data.task_description,
        started_at=data.started_at,
        ended_at=data.ended_at,
        duration_minutes=data.duration_minutes,
        attachment_filename=data.attachment_filename,
        attachment_text=data.attachment_text,
        notes=data.notes,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@router.get("", response_model=WorkLogListResponse)
async def list_work_logs(
    job_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List work logs with optional contract filter."""
    query = select(WorkLog).where(WorkLog.user_id == current_user.id)
    if job_id:
        query = query.where(WorkLog.job_id == job_id)
    query = query.order_by(WorkLog.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    logs = result.scalars().all()

    # Total count and minutes
    count_q = select(func.count()).select_from(WorkLog).where(WorkLog.user_id == current_user.id)
    if job_id:
        count_q = count_q.where(WorkLog.job_id == job_id)
    total = (await db.execute(count_q)).scalar() or 0

    minutes_q = select(func.sum(WorkLog.duration_minutes)).where(
        WorkLog.user_id == current_user.id,
        WorkLog.duration_minutes.isnot(None),
    )
    if job_id:
        minutes_q = minutes_q.where(WorkLog.job_id == job_id)
    total_minutes = (await db.execute(minutes_q)).scalar() or 0

    return WorkLogListResponse(logs=list(logs), total=total, total_minutes=total_minutes)


@router.patch("/{log_id}", response_model=WorkLogResponse)
async def update_work_log(
    log_id: str,
    data: WorkLogUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a work log (e.g., stop a running timer)."""
    result = await db.execute(
        select(WorkLog).where(WorkLog.id == log_id, WorkLog.user_id == current_user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work log not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(log, field, value)

    await db.commit()
    await db.refresh(log)
    return log


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work_log(
    log_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a work log."""
    result = await db.execute(
        select(WorkLog).where(WorkLog.id == log_id, WorkLog.user_id == current_user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work log not found")
    await db.delete(log)
    await db.commit()


@router.post("/extract-image", response_model=ExtractImageResponse)
async def extract_image_text(
    data: ExtractImageRequest,
    current_user: User = Depends(get_current_user),
):
    """Use gpt-4o-mini vision to extract text and context from a screenshot or document image."""
    # Normalise: accept raw base64 or data URL
    raw = data.image_base64
    if raw.startswith("data:"):
        # Extract the base64 portion after the comma
        raw = raw.split(",", 1)[-1]

    # Validate it looks like base64
    try:
        base64.b64decode(raw[:64])  # Quick sanity check
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    # Re-add data URL prefix for OpenAI vision API
    image_url = f"data:image/jpeg;base64,{raw}"

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.vision_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "This is a screenshot or document image related to a work task. "
                            "Please: 1) Extract any visible text verbatim. "
                            "2) Provide a 1-2 sentence summary of what the image shows. "
                            "Respond as JSON: {\"extracted_text\": \"...\", \"summary\": \"...\"}"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "low"},
                    },
                ],
            }
        ],
        response_format={"type": "json_object"},
        max_tokens=1000,
    )

    import json
    result = json.loads(response.choices[0].message.content)
    return ExtractImageResponse(
        extracted_text=result.get("extracted_text", ""),
        summary=result.get("summary", ""),
    )
