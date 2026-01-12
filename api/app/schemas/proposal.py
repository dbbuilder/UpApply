"""Schemas for proposals."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ProposalCreate(BaseModel):
    """Schema for creating a proposal."""

    cover_letter_text: str
    job_id: Optional[str] = None
    upwork_proposal_id: Optional[str] = None
    upwork_job_url: Optional[str] = None
    job_title: Optional[str] = None
    job_description_snippet: Optional[str] = None
    job_skills: Optional[List[str]] = None
    job_budget: Optional[str] = None
    job_category: Optional[str] = None
    bid_amount: Optional[float] = None
    bid_type: Optional[str] = None  # hourly, fixed
    status: Optional[str] = None
    submitted_at: Optional[datetime] = None
    source: str = "manual"  # manual, scraped, extension


class ProposalUpdate(BaseModel):
    """Schema for updating a proposal."""

    cover_letter_text: Optional[str] = None
    status: Optional[str] = None
    was_hired: Optional[bool] = None
    client_responded: Optional[bool] = None
    earnings: Optional[float] = None


class ProposalResponse(BaseModel):
    """Schema for proposal response."""

    id: str
    user_id: str
    job_id: Optional[str] = None
    upwork_proposal_id: Optional[str] = None
    upwork_job_url: Optional[str] = None
    cover_letter_text: str
    job_title: Optional[str] = None
    job_description_snippet: Optional[str] = None
    job_skills: Optional[List[str]] = None
    job_budget: Optional[str] = None
    job_category: Optional[str] = None
    bid_amount: Optional[float] = None
    bid_type: Optional[str] = None
    status: Optional[str] = None
    was_hired: Optional[bool] = None
    client_responded: Optional[bool] = None
    earnings: Optional[float] = None
    source: str
    submitted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProposalSearchRequest(BaseModel):
    """Schema for searching proposals by content similarity."""

    query: str  # Job description or search query
    limit: int = 5
    include_successful_only: bool = False


class ProposalSearchResult(BaseModel):
    """Schema for proposal search result."""

    proposal: ProposalResponse
    similarity: float


class ProposalBulkCreate(BaseModel):
    """Schema for bulk creating proposals (for import/scrape)."""

    proposals: List[ProposalCreate]


class ProposalImportFromUpwork(BaseModel):
    """Schema for importing proposals scraped from Upwork."""

    proposals: List[dict]  # Raw scraped data
