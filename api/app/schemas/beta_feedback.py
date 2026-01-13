"""Beta feedback schemas."""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr


class BetaFeedbackCreate(BaseModel):
    """Schema for creating beta feedback."""

    feedback_type: Literal["bug", "feature_request", "usability", "general"]
    description: str

    # Optional contact info
    email: Optional[EmailStr] = None

    # Context (auto-filled by extension)
    page_url: Optional[str] = None
    extension_version: Optional[str] = None
    browser_info: Optional[str] = None


class BetaFeedbackResponse(BaseModel):
    """Schema for beta feedback response."""

    id: str
    feedback_type: str
    description: str
    email: Optional[str] = None
    page_url: Optional[str] = None
    extension_version: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BetaFeedbackList(BaseModel):
    """Schema for listing beta feedback (admin use)."""

    items: list[BetaFeedbackResponse]
    total: int
