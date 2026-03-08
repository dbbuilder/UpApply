"""Schemas for job reviews (scored job ratings)."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, field_validator


class JobReviewUpsert(BaseModel):
    upwork_job_url: str
    upwork_job_id: Optional[str] = None
    job_title: str
    ai_score: Optional[float] = None
    chips: Optional[List[str]] = None
    budget_amount: Optional[str] = None
    budget_type: Optional[str] = None
    scored_at: Optional[datetime] = None


class JobReviewRate(BaseModel):
    user_rating: int
    user_comment: Optional[str] = None

    @field_validator('user_rating')
    @classmethod
    def rating_range(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError('user_rating must be 1–5')
        return v


class JobReviewResponse(BaseModel):
    id: str
    upwork_job_url: str
    upwork_job_id: Optional[str] = None
    job_title: str
    ai_score: Optional[float] = None
    chips: Optional[List[str]] = None
    budget_amount: Optional[str] = None
    budget_type: Optional[str] = None
    user_rating: Optional[int] = None
    user_comment: Optional[str] = None
    scored_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobReviewListResponse(BaseModel):
    reviews: List[JobReviewResponse]
    total: int
