"""Pydantic schemas for the job_queue endpoint."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, List, Literal, Optional, Union
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.services.skip_reasons import parse_stored

from app.schemas.job import (
    MAX_GEN_DESCRIPTION,
    MAX_GEN_SKILL_LENGTH,
    MAX_GEN_SKILLS,
    MAX_GEN_TITLE,
    ClientTrust,
)

MAX_INGEST_JOBS = 50
MAX_INGEST_URL = 500  # jobs.upwork_url is VARCHAR(500)
MAX_INGEST_SHORT = 200  # budget, posted/proposals text, client_info values


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


class IngestClientInfo(BaseModel):
    """client_info on an ingested job: the known keys only (others are dropped). Numbers are kept
    as text, as the extension's scraper and the job analysis (hire_rate "0%") read them."""

    model_config = ConfigDict(extra="ignore")

    payment_verified: Optional[Union[bool, Annotated[str, Field(max_length=MAX_INGEST_SHORT)]]] = None
    rating: Optional[Annotated[str, Field(max_length=MAX_INGEST_SHORT)]] = None
    total_spent: Optional[Annotated[str, Field(max_length=MAX_INGEST_SHORT)]] = None
    hire_rate: Optional[Annotated[str, Field(max_length=MAX_INGEST_SHORT)]] = None
    jobs_posted: Optional[Annotated[str, Field(max_length=MAX_INGEST_SHORT)]] = None
    location: Optional[Annotated[str, Field(max_length=MAX_INGEST_SHORT)]] = None
    proposals: Optional[Annotated[str, Field(max_length=MAX_INGEST_SHORT)]] = None

    @field_validator("rating", "total_spent", "hire_rate", "jobs_posted", "location", "proposals",
                     mode="before")
    @classmethod
    def _number_as_text(cls, v):
        return str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


class IngestJob(BaseModel):
    """One job the extension gathered from an Upwork search page."""

    upwork_url: str = Field(..., min_length=1, max_length=MAX_INGEST_URL)
    title: str = Field(..., min_length=1, max_length=MAX_GEN_TITLE)
    description: str = Field("", max_length=MAX_GEN_DESCRIPTION)
    skills: List[Annotated[str, Field(max_length=MAX_GEN_SKILL_LENGTH)]] = Field(
        default_factory=list, max_length=MAX_GEN_SKILLS
    )
    budget_amount: Optional[str] = Field(None, max_length=MAX_INGEST_SHORT)
    budget_type: Optional[Literal["fixed", "hourly"]] = None
    posted_at: Optional[str] = Field(None, max_length=64)  # ISO-8601; unreadable values are ignored
    posted_text: Optional[str] = Field(None, max_length=MAX_INGEST_SHORT)  # e.g. "2 hours ago"
    client_info: Optional[IngestClientInfo] = None
    proposals_text: Optional[str] = Field(None, max_length=MAX_INGEST_SHORT)

    @field_validator("description", mode="before")
    @classmethod
    def _none_description(cls, v):
        return "" if v is None else v

    @field_validator("upwork_url")
    @classmethod
    def _upwork_url(cls, v: str) -> str:
        v = v.strip()
        parsed = urlparse(v)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or not (host == "upwork.com" or host.endswith(".upwork.com")):
            raise ValueError("upwork_url must be an http(s) upwork.com URL")
        return v


class JobQueueIngestRequest(BaseModel):
    """Body for POST /api/v1/job-queue/ingest (extension → jobs from one search page)."""

    query_id: Optional[str] = Field(None, max_length=36)
    query: Optional[str] = Field(None, max_length=MAX_INGEST_SHORT)
    jobs: List[IngestJob] = Field(..., max_length=MAX_INGEST_JOBS)


class JobQueueIngestResponse(BaseModel):
    """received = duplicates + pre_filtered + scored; scored = suggested + below_threshold.
    queued_ids are the new "suggested" items (the ones the user reviews)."""

    received: int
    duplicates: int
    pre_filtered: int
    scored: int
    suggested: int
    below_threshold: int
    queued_ids: List[str]


class JobQueueActionRequest(BaseModel):
    """Body for PUT /api/v1/job-queue/{id}/action."""

    action: str  # "approve" | "reject"
    # A code from app.services.skip_reasons.USER_REASONS, optionally "code: note";
    # anything else is stored as "other: <text>"
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
    # Stored as "<code>" or "<code>: <text>" (app.services.skip_reasons), e.g.
    # "budget_too_low", "pre_filter:blocked_country: India". Legacy values are mapped by
    # skip_reason / skip_reason_detail below.
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
    client_trust: Optional[ClientTrust] = None  # computed on GET /job-queue only

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def skip_reason(self) -> Optional[str]:
        """Canonical skip code for rejected / pre_filtered items (legacy values mapped)."""
        return parse_stored(self.rejection_reason, self.status)[0]

    @computed_field
    @property
    def skip_reason_detail(self) -> Optional[str]:
        """Free text kept with the code (user note, or pre-filter detail such as the country)."""
        return parse_stored(self.rejection_reason, self.status)[1]


class DraftSubmitResponse(BaseModel):
    edit_distance_pct: float
    avg_edit_distance: Optional[float]
    message: str


class ConfirmSubmitResponse(BaseModel):
    status: str
    message: str
    autonomy_level: int
