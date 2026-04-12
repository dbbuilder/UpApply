"""Pydantic schemas for the job_queue endpoint."""
from datetime import datetime
from decimal import Decimal
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
    # If set, item is created with status=pre_filtered; rejection_reason stores this value
    filter_reason: Optional[str] = None


class JobQueueActionRequest(BaseModel):
    """Body for PUT /api/v1/job-queue/{id}/action."""

    action: str  # "approve" | "reject"
    rejection_reason: Optional[str] = None


class DraftSubmitRequest(BaseModel):
    """Body for POST /api/v1/job-queue/{id}/submit-edit."""

    final_text: str
    auto_filled: bool = False


class ConfirmSubmitRequest(BaseModel):
    """Body for POST /api/v1/job-queue/{id}/confirm-submit.

    Called when the user confirms the auto-fill modal (before the apply tab opens).
    Records the bid amount and connects the user intends to spend.
    """

    bid_amount: Optional[Decimal] = None
    connects_spent: Optional[int] = None
    # Upwork proposal ID may not be available until after submission; can be patched later
    upwork_proposal_id: Optional[str] = None


class ProposalResponseRequest(BaseModel):
    """Body for POST /api/v1/job-queue/{id}/proposal-response.

    Called by the background script when it detects a status change on a proposal.
    response_type: viewed | responded | invited | declined
    """

    response_type: str
    upwork_proposal_id: Optional[str] = None


# ── Response schemas ─────────────────────────────────────────────────────────

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
    # When status="pre_filtered", rejection_reason holds the filter reason code
    # e.g. "blocked_country (India)", "budget_too_low ($300 < $500)"
    draft_cover_letter: Optional[str] = None
    draft_status: Optional[str] = None
    draft_generated_at: Optional[datetime] = None
    bid_amount: Optional[Decimal] = None
    connects_spent: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    upwork_proposal_id: Optional[str] = None
    client_response_type: Optional[str] = None
    client_response_at: Optional[datetime] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DraftSubmitResponse(BaseModel):
    edit_distance_pct: float
    avg_edit_distance: Optional[float]
    message: str


class ConfirmSubmitResponse(BaseModel):
    status: str
    message: str
    autonomy_level: int
