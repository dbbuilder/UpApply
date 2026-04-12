"""Pydantic schemas for the job_queue endpoint."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Request schemas ──────────────────────────────────────────────────────────

class JobQueueCreate(BaseModel):
    """Body for POST /api/v1/job-queue (agent → adds discovered job)."""

    upwork_url: str
    title: str
    description: Optional[str] = None
    skills: Optional[List[str]] = Field(default_factory=list)
    budget_amount: Optional[str] = None
    budget_type: Optional[str] = None
    client_info: Optional[dict] = None
    ai_score: Optional[float] = None
    ai_reasoning: Optional[str] = None
    chips: Optional[List[str]] = Field(default_factory=list)
    source: str = "agent"
    source_query_id: Optional[str] = None


class JobQueueActionRequest(BaseModel):
    """Body for PUT /api/v1/job-queue/{id}/action."""

    action: str  # "approve" | "reject"
    rejection_reason: Optional[str] = None


# ── Response schema ──────────────────────────────────────────────────────────

class JobQueueItemResponse(BaseModel):
    """Full representation of a job_queue row."""

    id: str
    user_id: str
    upwork_url: str
    title: str
    description: Optional[str] = None
    skills: Optional[List[str]] = None
    budget_amount: Optional[str] = None
    budget_type: Optional[str] = None
    client_info: Optional[dict] = None
    ai_score: Optional[float] = None
    ai_reasoning: Optional[str] = None
    chips: Optional[List[str]] = None
    status: str
    source: str
    source_query_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
