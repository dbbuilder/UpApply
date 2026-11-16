"""Schemas for job reviews (scored job ratings)."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class JobReviewDetails(BaseModel):
    """What the job card showed when it was scored (Find tab display and filters)."""
    posted_at: Optional[datetime] = None
    posted_text: Optional[str] = Field(None, max_length=60)
    client_country: Optional[str] = Field(None, max_length=80)
    client_spent: Optional[str] = Field(None, max_length=40)
    client_rating: Optional[str] = Field(None, max_length=20)
    payment_verified: Optional[bool] = None
    proposals: Optional[str] = Field(None, max_length=40)
    experience_level: Optional[str] = Field(None, max_length=40)

    model_config = {"extra": "ignore"}


class JobReviewUpsert(BaseModel):
    upwork_job_url: str
    upwork_job_id: Optional[str] = None
    job_title: str
    ai_score: Optional[float] = None
    chips: Optional[List[str]] = None
    budget_amount: Optional[str] = None
    budget_type: Optional[str] = None
    scored_at: Optional[datetime] = None
    details: Optional[JobReviewDetails] = None


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
    details: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobReviewListResponse(BaseModel):
    reviews: List[JobReviewResponse]
    total: int
