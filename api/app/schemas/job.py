"""Job schemas."""
from datetime import datetime
from typing import Annotated, Optional, List
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator, model_validator

# Free-text limits on generation requests (untrusted client text reaches LLM prompts)
MAX_GEN_TITLE = 300
MAX_GEN_DESCRIPTION = 20000
MAX_SCREENING_QUESTION = 2000
MAX_SCREENING_QUESTIONS = 20
MAX_EXTRA_POINTS = 2000
MAX_PROTOTYPE_URL = 500
MAX_GEN_SKILLS = 50
MAX_GEN_SKILL_LENGTH = 200

ScreeningQuestion = Annotated[str, Field(max_length=MAX_SCREENING_QUESTION)]


class ClientInfo(BaseModel):
    """Schema for client information."""

    rating: Optional[float] = None
    location: Optional[str] = None
    hire_rate: Optional[str] = None
    total_spent: Optional[str] = None
    member_since: Optional[str] = None


class TrustSignal(BaseModel):
    """One line of the client trust card."""

    label: str
    value: str
    effect: str  # positive | neutral | caution


class ClientTrust(BaseModel):
    """Client trust card (app/services/client_trust.py); separate from match_score."""

    tier: str  # High Confidence | Proceed with Caution | Suspicious
    signals: List[TrustSignal]
    notes: List[str] = []


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
    client_trust: Optional[ClientTrust] = None  # set by POST /jobs only

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
    upwork_url: Optional[str] = None  # lets repost detection skip this job itself


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
    client_trust: Optional[ClientTrust] = None


class CoverLetterGenerateRequest(BaseModel):
    """Schema for cover letter generation request."""

    job_id: Optional[str] = None  # If job already saved
    job_data: Optional[JobCreate] = None  # Or provide job data directly

    # Generation options
    tone: Optional[str] = None  # Override user's default tone
    max_length: int = 300  # Max words
    focus_skills: Optional[List[str]] = None  # Skills to emphasize
    custom_instructions: Optional[str] = Field(None, max_length=MAX_EXTRA_POINTS)  # Additional instructions
    prototype_url: Optional[str] = Field(None, max_length=MAX_PROTOTYPE_URL)  # URL to a prototype built for this job
    include_call_offer: bool = True  # Append no-cost/no-commitment call offer before close
    screening_questions: Optional[List[ScreeningQuestion]] = Field(
        None, max_length=MAX_SCREENING_QUESTIONS
    )  # v2: answered jointly with the letter

    @field_validator("prototype_url")
    @classmethod
    def _http_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc or any(c.isspace() for c in v):
            raise ValueError("prototype_url must be an http(s) URL")
        return v

    @model_validator(mode="after")
    def _job_data_limits(self):
        if self.job_data:
            if len(self.job_data.title) > MAX_GEN_TITLE:
                raise ValueError(f"job_data.title exceeds {MAX_GEN_TITLE} characters")
            if len(self.job_data.description) > MAX_GEN_DESCRIPTION:
                raise ValueError(f"job_data.description exceeds {MAX_GEN_DESCRIPTION} characters")
            skills = self.job_data.skills_required or []
            if len(skills) > MAX_GEN_SKILLS or any(len(s) > MAX_GEN_SKILL_LENGTH for s in skills):
                raise ValueError(
                    f"job_data.skills_required allows {MAX_GEN_SKILLS} skills of {MAX_GEN_SKILL_LENGTH} characters"
                )
        return self


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

    # Generation v2 (None on the legacy path)
    screening_answers: Optional[List[dict]] = None
    verify_warnings: Optional[List[str]] = None
    facts_used: Optional[List[dict]] = None  # [{id, statement}] of facts the draft cites
    claims_verified: Optional[bool] = None  # False when the claim check was skipped

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


MAX_REFINE_MESSAGE = 4000
MAX_FINAL_TEXT = 20000
MAX_FINAL_ANSWER = 5000


class QAPair(BaseModel):
    """One screening question and its answer."""

    question: str = Field(..., max_length=MAX_SCREENING_QUESTION)
    answer: str = Field(..., max_length=MAX_FINAL_ANSWER)


class CoverLetterRefineRequest(BaseModel):
    """One refine-thread message from the user."""

    message: str = Field(..., max_length=MAX_REFINE_MESSAGE)
    # The draft as the sidebar shows it (includes hand edits); falls back to the stored letter
    current_draft: Optional[str] = Field(None, max_length=MAX_FINAL_TEXT)
    # Sidebar's current answers (includes hand edits); falls back to the thread's last answers
    screening_answers: Optional[List[QAPair]] = Field(None, max_length=MAX_SCREENING_QUESTIONS)


class CoverLetterRefineResponse(BaseModel):
    """Revised draft after one refine turn."""

    cover_letter: str
    screening_answers: List[QAPair]
    warnings: List[str]
    refine_messages: List[dict]
    claims_verified: bool = True  # False when the claim check was skipped for this draft


class CoverLetterFinalRequest(BaseModel):
    """What was actually submitted on Upwork (captured on Submit click)."""

    final_text: str = Field(..., max_length=MAX_FINAL_TEXT)
    final_answers: Optional[List[QAPair]] = Field(None, max_length=MAX_SCREENING_QUESTIONS)


class CoverLetterFinalResponse(BaseModel):
    """Result of recording the submitted text."""

    id: str
    edit_distance_pct: float
    author: str  # chris | chris_edited_ai
    proposal_id: Optional[str] = None
    fact_candidates: int


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
