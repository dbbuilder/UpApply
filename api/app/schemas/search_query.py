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


class QueryCoverage(BaseModel):
    """Coverage of a single existing query against the winning job set."""
    query_id: str
    query: str
    url_params: Optional[str] = None
    coverage_count: int        # how many target jobs this query's keywords match
    coverage_pct: float        # percentage of target jobs covered
    sample_matches: list[str]  # up to 3 matched job titles


class SuggestedQuery(BaseModel):
    """A new search query suggested by the Search Lab."""
    query: str
    url_params: str            # full Upwork search params
    reasoning: str             # why this covers gaps
    gap_jobs_targeted: list[str]   # which uncovered job titles this addresses


class SearchLabResult(BaseModel):
    """Full output of POST /search-queries/evaluate."""
    total_target_jobs: int
    covered_count: int
    coverage_pct: float
    query_coverage: list[QueryCoverage]
    gap_jobs: list[str]           # titles of target jobs not covered by any query
    suggestions: list[SuggestedQuery]
    evaluated_at: str             # ISO datetime string


class QueryExperimentResult(BaseModel):
    """Per-query live experiment data from running a search on Upwork."""
    query_id: str
    query: str
    url_params: Optional[str] = None
    jobs_returned: int
    avg_score: float
    high_score_count: int
    sample_good_titles: list[str] = []
    sample_bad_titles: list[str] = []


class OptimizeRequest(BaseModel):
    """Body for POST /search-queries/optimize."""
    experiments: list[QueryExperimentResult]


class QueryVariant(BaseModel):
    """A suggested replacement or supplement for a weak search query."""
    query: str
    url_params: str
    reasoning: str
    change_type: str   # "broader" | "narrower" | "reframe"


class QueryOptimization(BaseModel):
    """Grade + variants for one search query."""
    query_id: str
    original_query: str
    grade: str          # "strong" | "low_volume" | "low_quality" | "both"
    inclusive_score: float   # high_score_count from this experiment run
    variants: list[QueryVariant]


class OptimizeResult(BaseModel):
    """Full output of POST /search-queries/optimize."""
    optimizations: list[QueryOptimization]
    evaluated_at: str
