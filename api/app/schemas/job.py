"""Job schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ClientInfo(BaseModel):
    """Schema for client information."""

    rating: Optional[float] = None
    location: Optional[str] = None
    hire_rate: Optional[str] = None
    total_spent: Optional[str] = None
    member_since: Optional[str] = None


class JobCreate(BaseModel):
    """Schema for creating/submitting a job from extension."""

    upwork_url: str
    title: str
    description: str

    # Budget
    budget_type: Optional[str] = None  # hourly, fixed
    budget_amount: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None

    # Skills & requirements
    skills_required: Optional[List[str]] = None
    experience_level: Optional[str] = None
    project_length: Optional[str] = None

    # Client
    client_info: Optional[ClientInfo] = None

    # Upwork-specific
    upwork_job_id: Optional[str] = None
    posted_date: Optional[datetime] = None


class JobResponse(BaseModel):
    """Schema for job response."""

    id: str
    user_id: str
    upwork_url: str
    upwork_job_id: Optional[str] = None
    title: str
    description: str

    budget_type: Optional[str] = None
    budget_amount: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None

    skills_required: Optional[List[str]] = None
    experience_level: Optional[str] = None
    project_length: Optional[str] = None

    client_info: Optional[dict] = None

    match_score: Optional[float] = None
    analysis: Optional[dict] = None

    # Full job posting data
    full_description: Optional[str] = None
    attachment_text: Optional[str] = None
    attachment_metadata: Optional[List[dict]] = None

    is_saved: bool = False
    source: Optional[str] = None
    expires_at: Optional[datetime] = None
    search_query_id: Optional[str] = None

    posted_date: Optional[datetime] = None
    scraped_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SkillMatch(BaseModel):
    """Schema for a skill match."""

    skill: str
    match_type: str  # exact, related, missing
    user_level: Optional[str] = None
    relevance_score: float


class JobAnalysisRequest(BaseModel):
    """Schema for job analysis request (analyze without saving)."""

    title: str
    description: str
    skills_required: Optional[List[str]] = None
    budget_type: Optional[str] = None
    budget_amount: Optional[str] = None
    experience_level: Optional[str] = None
    client_info: Optional[ClientInfo] = None


class JobAnalysisResponse(BaseModel):
    """Schema for job analysis response."""

    match_score: float  # 0-100
    skill_matches: List[SkillMatch]
    missing_skills: List[str]
    strengths: List[str]
    concerns: List[str]
    deal_breaker_warnings: List[str]
    relevant_memories: List[dict]  # Memory summaries
    recommendation: str  # Overall recommendation
    reason: Optional[str] = None  # One-sentence LLM scoring reason


class CoverLetterGenerateRequest(BaseModel):
    """Schema for cover letter generation request."""

    job_id: Optional[str] = None  # If job already saved
    job_data: Optional[JobCreate] = None  # Or provide job data directly

    # Generation options
    tone: Optional[str] = None  # Override user's default tone
    max_length: int = 300  # Max words
    focus_skills: Optional[List[str]] = None  # Skills to emphasize
    custom_instructions: Optional[str] = None  # Additional instructions
    prototype_url: Optional[str] = None  # URL to a prototype built for this job
    include_call_offer: bool = True  # Append no-cost/no-commitment call offer before close


class CoverLetterResponse(BaseModel):
    """Schema for cover letter response."""

    id: str
    user_id: str
    job_id: str
    content: str

    model_used: str
    memories_used: Optional[List[str]] = None

    word_count: Optional[int] = None
    version: int = 1
    is_final: bool = False

    created_at: datetime

    # Include match analysis
    match_score: Optional[float] = None
    highlighted_skills: Optional[List[str]] = None

    model_config = {"from_attributes": True}


class CoverLetterRegenerateRequest(BaseModel):
    """Schema for regenerating a cover letter."""

    tone: Optional[str] = None
    max_length: Optional[int] = None
    focus_skills: Optional[List[str]] = None
    custom_instructions: Optional[str] = None
    feedback: Optional[str] = None  # What to improve
    include_call_offer: bool = True


class CoverLetterSubmitRequest(BaseModel):
    """Mark a cover letter as submitted and capture the final text."""

    submitted_text: str  # What was actually sent (may differ from generated)


class CoverLetterImproveResponse(BaseModel):
    """Response from the self-improvement endpoint."""

    cover_letter_id: str       # New version id
    improved_content: str
    improvement_notes: List[str]
    hired_examples_used: int   # How many won letters were compared against


# Attachment extraction schemas

class AttachmentData(BaseModel):
    """Schema for a single attachment to extract text from."""

    data: str  # Base64-encoded file content
    filename: str
    content_type: str


class AttachmentMetadata(BaseModel):
    """Schema for attachment extraction metadata."""

    filename: str
    content_type: str
    size: int
    extraction_status: str  # success, partial, failed, unsupported
    error: Optional[str] = None


class ExtractAttachmentsRequest(BaseModel):
    """Schema for attachment extraction request."""

    attachments: List[AttachmentData]
    full_description: Optional[str] = None  # Complete job description from posting page


class ExtractAttachmentsResponse(BaseModel):
    """Schema for attachment extraction response."""

    job_id: str
    attachment_text: str
    full_description: Optional[str] = None
    attachment_count: int
    attachment_metadata: List[AttachmentMetadata]
    extraction_errors: List[str]


class JobImportItem(BaseModel):
    """A single job from a saved list or search results page."""

    upwork_job_id: str
    upwork_url: str
    title: str
    description: str  # snippet is fine
    job_type: Optional[str] = None  # "hourly" | "fixed"
    experience_level: Optional[str] = None
    posted_date_raw: Optional[str] = None  # relative string like "2 hours ago"
    client_info: Optional[dict] = None
    skills: Optional[List[str]] = None


class JobBulkImportRequest(BaseModel):
    """Import multiple jobs from saved list or search results."""

    jobs: List[JobImportItem]
    source: str  # "saved" | "search"
    search_query: Optional[str] = None  # populated for source="search"
    search_query_id: Optional[str] = None  # FK to search_queries.id


class ContractImportItem(BaseModel):
    """A single contract from the Upwork contracts page."""

    contract_id: str
    title: str
    contract_type: str  # "hourly" | "fixed" | "unknown"
    rate: Optional[str] = None
    status: str  # "active" | "paused" | "ended"
    client_name: Optional[str] = None
    date_range: Optional[str] = None
    cover_letter_text: Optional[str] = None  # Winning proposal text, if scraped


class ContractImportRequest(BaseModel):
    """Import multiple contracts from Upwork contract history."""

    contracts: List[ContractImportItem]


class ContractImportResponse(BaseModel):
    """Response for contract import operation."""

    imported: int
    updated: int
    total: int


class MilestoneSuggestion(BaseModel):
    """A single milestone suggestion."""

    description: str
    days_from_start: int  # e.g. 14, 30, 45
    amount: float


class SuggestMilestonesRequest(BaseModel):
    """Request to suggest milestones for a fixed-price job."""

    job_title: str
    job_description: str
    budget_amount: Optional[str] = None  # e.g. "$500", "$1,500"
    num_milestones: int = 3


class SuggestMilestonesResponse(BaseModel):
    """Response containing milestone suggestions."""

    milestones: List[MilestoneSuggestion]
