"""Pydantic schemas for search query management."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class SearchQueryCreate(BaseModel):
    """Schema for creating a new saved search query."""

    query: str
    url_params: Optional[str] = None
    source: str = "manual"

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        return v

    @field_validator("source")
    @classmethod
    def valid_source(cls, v: str) -> str:
        allowed = {"manual", "ai_generated", "seeded", "imported"}
        if v not in allowed:
            raise ValueError(f"source must be one of {allowed}")
        return v


class SearchQueryResponse(BaseModel):
    """Schema for returning a search query with computed stats."""

    id: str
    query: str
    url_params: Optional[str] = None
    source: str
    active: bool
    run_count: int
    last_run_at: Optional[datetime] = None
    total_jobs_found: int
    avg_match_score: Optional[float] = None
    high_score_count: int
    performance_score: float
    is_stale: bool
    is_low_performer: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RunRecordRequest(BaseModel):
    """Body for POST /search-queries/{id}/record-run."""

    jobs_found: int
    avg_score: float
    high_score_count: int  # number of jobs scoring >= 70


class BulkImportSearchQueriesRequest(BaseModel):
    """Body for POST /search-queries/bulk-import."""

    queries: list[dict]  # [{query, url_params?, source?}]
