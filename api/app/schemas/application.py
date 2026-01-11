"""Application schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.models.application import ApplicationStatus


class ApplicationCreate(BaseModel):
    """Schema for creating an application record."""

    job_id: str
    cover_letter_id: Optional[str] = None
    bid_amount: Optional[float] = None
    status: ApplicationStatus = ApplicationStatus.DRAFT


class ApplicationUpdate(BaseModel):
    """Schema for updating an application."""

    status: Optional[ApplicationStatus] = None
    bid_amount: Optional[float] = None
    cover_letter_id: Optional[str] = None


class ApplicationOutcome(BaseModel):
    """Schema for recording application outcome."""

    status: ApplicationStatus
    outcome_notes: Optional[str] = None
    client_response: Optional[str] = None
    earnings: Optional[float] = None


class ApplicationResponse(BaseModel):
    """Schema for application response."""

    id: str
    user_id: str
    job_id: str
    cover_letter_id: Optional[str] = None

    status: ApplicationStatus
    bid_amount: Optional[float] = None

    outcome_notes: Optional[str] = None
    client_response: Optional[str] = None
    earnings: Optional[float] = None

    submitted_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    outcome_recorded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationStats(BaseModel):
    """Schema for application statistics."""

    total_applications: int
    submitted: int
    viewed: int
    responded: int
    hired: int
    declined: int

    response_rate: float  # % that got responses
    success_rate: float  # % that got hired

    total_earnings: float
    avg_match_score: Optional[float] = None
