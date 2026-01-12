"""Schemas for screening answers."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ScreeningAnswerCreate(BaseModel):
    """Schema for creating a screening answer."""

    question: str
    answer: str
    question_type: Optional[str] = None  # experience, availability, rate, technical, general
    job_id: Optional[str] = None
    application_id: Optional[str] = None
    job_title: Optional[str] = None
    job_skills: Optional[List[str]] = None


class ScreeningAnswerUpdate(BaseModel):
    """Schema for updating a screening answer."""

    answer: Optional[str] = None
    was_successful: Optional[bool] = None


class ScreeningAnswerResponse(BaseModel):
    """Schema for screening answer response."""

    id: str
    user_id: str
    job_id: Optional[str] = None
    application_id: Optional[str] = None
    question: str
    answer: str
    question_type: Optional[str] = None
    job_title: Optional[str] = None
    was_successful: Optional[bool] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScreeningAnswerSearchRequest(BaseModel):
    """Schema for searching screening answers by question similarity."""

    question: str
    limit: int = 5


class ScreeningAnswerSearchResult(BaseModel):
    """Schema for screening answer search result."""

    answer: ScreeningAnswerResponse
    similarity: float


class ScreeningAnswerBulkCreate(BaseModel):
    """Schema for bulk creating screening answers."""

    answers: List[ScreeningAnswerCreate]
