"""Learned rules (rules proposed from the user's own edits)."""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

RuleStatus = Literal["proposed", "accepted", "rejected"]


class LearnedRuleOut(BaseModel):
    id: str
    rule: str
    evidence_quote: str
    times_seen: int
    status: str
    created_at: datetime
    decided_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LearnedRuleDecision(BaseModel):
    status: Literal["accepted", "rejected"]


class LearnedRuleDecisionOut(LearnedRuleOut):
    # Set on accept for users with a voice kit: the kit repo stays the source of truth.
    note: Optional[str] = None


class LearnedRuleProposeOut(BaseModel):
    proposed: List[LearnedRuleOut]
    pairs_found: int  # meaningful (≥5% changed) draft → sent pairs considered
    refine_requests_found: int
