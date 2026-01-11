"""Feedback schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class FeedbackCreate(BaseModel):
    """Schema for creating feedback."""

    application_id: Optional[str] = None
    cover_letter_id: Optional[str] = None

    feedback_type: str  # thumbs_up, thumbs_down, edited, regenerated, outcome
    rating: Optional[int] = None  # 1-5
    comment: Optional[str] = None

    # Edit tracking
    original_text: Optional[str] = None
    edited_text: Optional[str] = None

    was_helpful: Optional[bool] = None
    would_use_again: Optional[bool] = None


class FeedbackResponse(BaseModel):
    """Schema for feedback response."""

    id: str
    user_id: str
    application_id: Optional[str] = None
    cover_letter_id: Optional[str] = None

    feedback_type: str
    rating: Optional[int] = None
    comment: Optional[str] = None

    was_helpful: Optional[bool] = None
    would_use_again: Optional[bool] = None

    created_at: datetime

    model_config = {"from_attributes": True}


class AnalyticsDashboard(BaseModel):
    """Schema for analytics dashboard data."""

    # Application stats
    total_applications: int
    response_rate: float
    interview_rate: float
    hire_rate: float

    # Averages
    avg_match_score: Optional[float] = None
    avg_time_to_response_days: Optional[float] = None

    # Top performing
    top_skills: list  # [{skill, success_rate}]
    top_industries: list  # [{industry, success_rate}]

    # Trends
    weekly_applications: list  # [{week, applications, responses}]

    # Learning insights
    insights: list  # [{type, message, confidence}]
