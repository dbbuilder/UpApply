"""Pydantic schemas for the guardrail config endpoints."""
from typing import Optional

from pydantic import BaseModel, Field


class GuardrailConfigResponse(BaseModel):
    """Full guardrail config for the current user."""

    enabled: bool
    max_proposals_per_day: int
    min_connects_reserve: int
    max_bid_hourly: Optional[float] = None
    max_bid_fixed: Optional[float] = None
    min_score_threshold: float
    pause_start_hour: Optional[int] = None
    pause_end_hour: Optional[int] = None
    connects_balance: Optional[int] = None
    digest_email: Optional[str] = None

    model_config = {"from_attributes": True}


class GuardrailConfigUpdate(BaseModel):
    """Fields that can be updated on a guardrail config.

    All fields are optional — only supplied fields are updated (PATCH semantics).
    """

    enabled: Optional[bool] = None
    max_proposals_per_day: Optional[int] = Field(None, ge=1, le=50)
    min_connects_reserve: Optional[int] = Field(None, ge=0, le=500)
    max_bid_hourly: Optional[float] = Field(None, ge=0)
    max_bid_fixed: Optional[float] = Field(None, ge=0)
    min_score_threshold: Optional[float] = Field(None, ge=0.0, le=100.0)
    pause_start_hour: Optional[int] = Field(None, ge=0, le=23)
    pause_end_hour: Optional[int] = Field(None, ge=0, le=23)
    connects_balance: Optional[int] = Field(None, ge=0)
    digest_email: Optional[str] = None
