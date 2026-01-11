"""Memory schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class MemoryCreate(BaseModel):
    """Schema for creating a memory."""

    title: str
    content: str
    category: Optional[str] = None  # project, achievement, feedback, lesson, skill_demo

    # Context
    skills_demonstrated: Optional[List[str]] = None
    industry: Optional[str] = None
    project_type: Optional[str] = None
    client_type: Optional[str] = None

    # Outcomes
    outcome: Optional[str] = None
    metrics: Optional[dict] = None  # {revenue, time_saved, etc}
    client_feedback: Optional[str] = None

    # Metadata
    source: Optional[str] = "manual"  # manual, resume_import, job_won
    importance_score: float = 0.5


class MemoryUpdate(BaseModel):
    """Schema for updating a memory."""

    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None

    skills_demonstrated: Optional[List[str]] = None
    industry: Optional[str] = None
    project_type: Optional[str] = None
    client_type: Optional[str] = None

    outcome: Optional[str] = None
    metrics: Optional[dict] = None
    client_feedback: Optional[str] = None

    importance_score: Optional[float] = None


class MemoryResponse(BaseModel):
    """Schema for memory response."""

    id: str
    user_id: str
    title: str
    content: str
    category: Optional[str] = None

    skills_demonstrated: Optional[List[str]] = None
    industry: Optional[str] = None
    project_type: Optional[str] = None
    client_type: Optional[str] = None

    outcome: Optional[str] = None
    metrics: Optional[dict] = None
    client_feedback: Optional[str] = None

    source: Optional[str] = None
    importance_score: float = 0.5

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemorySearchRequest(BaseModel):
    """Schema for semantic memory search."""

    query: str
    limit: int = 5
    threshold: float = 0.5  # Minimum similarity score
    category: Optional[str] = None  # Filter by category
    skills: Optional[List[str]] = None  # Filter by skills


class MemorySearchResult(BaseModel):
    """Schema for memory search result."""

    memory: MemoryResponse
    similarity: float
    relevance_explanation: Optional[str] = None


class MemoryBulkImport(BaseModel):
    """Schema for bulk importing memories."""

    memories: List[MemoryCreate]
