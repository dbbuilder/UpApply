"""Fact (knowledge layer) schemas."""
from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

FactKind = Literal["project", "metric", "credential", "client_quote", "role", "tech", "outcome"]
FactStatus = Literal["candidate", "approved", "rejected"]
JobType = Literal["cto", "saas", "sql", "cloud", "ai", "fullstack"]

# Free-text request limits (column sizes: source_type String(50), source_ref String(200)).
MAX_STATEMENT = 2_000
MAX_DETAIL = 5_000
MAX_TAG = 100
MAX_TAGS = 50
MAX_INGEST_TEXT = 50_000

TagStr = Annotated[str, Field(max_length=MAX_TAG)]


class FactCandidate(BaseModel):
    """An extracted (or manually entered) claim, before dedupe/merge."""

    kind: FactKind
    statement: str
    detail: Optional[str] = None
    skills: List[str] = []
    industries: List[str] = []
    job_types: List[JobType] = []
    strength: float = Field(0.5, ge=0.0, le=1.0)
    source_type: str
    source_ref: Optional[str] = None
    source_snippet: Optional[str] = None  # verbatim evidence shown in the Facts review page


class FactCreate(BaseModel):
    """Manual fact entered by the user — stored approved."""

    kind: FactKind
    statement: str = Field(..., min_length=1, max_length=MAX_STATEMENT)
    detail: Optional[str] = Field(None, max_length=MAX_DETAIL)
    skills: List[TagStr] = Field([], max_length=MAX_TAGS)
    industries: List[TagStr] = Field([], max_length=MAX_TAGS)
    job_types: List[JobType] = []
    strength: float = Field(0.7, ge=0.0, le=1.0)


class FactUpdate(BaseModel):
    statement: Optional[str] = Field(None, min_length=1, max_length=MAX_STATEMENT)
    detail: Optional[str] = Field(None, max_length=MAX_DETAIL)
    status: Optional[FactStatus] = None
    kind: Optional[FactKind] = None
    skills: Optional[List[TagStr]] = Field(None, max_length=MAX_TAGS)
    job_types: Optional[List[JobType]] = None
    strength: Optional[float] = Field(None, ge=0.0, le=1.0)
    doubtful: Optional[bool] = None


class FactOut(BaseModel):
    id: str
    kind: str
    statement: str
    detail: Optional[str] = None
    skills: List[str] = []
    industries: List[str] = []
    job_types: List[str] = []
    strength: float
    status: str
    doubtful: bool = False
    source_type: str
    source_ref: Optional[str] = None
    sources: List[dict] = []
    times_used: int = 0
    times_in_won: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FactIngestItem(BaseModel):
    # text written by the user (the only extraction source)
    text: str = Field(..., max_length=MAX_INGEST_TEXT)
    source_ref: Optional[str] = Field(None, max_length=200)
    # not-the-user text that helps interpretation; never extracted
    context: Optional[str] = Field(None, max_length=MAX_INGEST_TEXT)


class FactIngestRequest(BaseModel):
    source_type: str = Field(..., min_length=1, max_length=50)
    items: List[FactIngestItem] = Field(..., max_length=25)
    auto_approve: bool = False


class FactIngestResult(BaseModel):
    created: int = 0
    merged: int = 0
    auto_approved: int = 0
    skipped: int = 0    # source_ref already ingested
    failed: int = 0     # extraction errors
    remaining: int = 0  # from-proposals: proposals still to process


class FactBulkApprove(BaseModel):
    ids: List[str] = Field(..., max_length=500)
