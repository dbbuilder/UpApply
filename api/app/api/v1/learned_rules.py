"""Learned rules: propose writing rules from the user's own edits; the user accepts or rejects."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import generation_unavailable
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.models.learned_rule import LearnedRule
from app.models.user import User
from app.schemas.learned_rule import (
    LearnedRuleDecision,
    LearnedRuleDecisionOut,
    LearnedRuleOut,
    LearnedRuleProposeOut,
    RuleStatus,
)
from app.services.generation.voice import load_voice
from app.services.learned_rules import propose_rules
from app.services.llm import LLMError

router = APIRouter()

VOICE_KIT_REPO = "dbbuilder-org/sv-writing-style"


def voice_kit_note(email: Optional[str]) -> Optional[str]:
    """For voice-kit users: the kit stays the source of truth, so the rule should be copied there."""
    voice = load_voice(email)
    if not voice:
        return None
    writer = voice.get("writer") or "your writer"
    return (
        f"You have a voice kit: copy this rule to {writer}/feedback-log.md in {VOICE_KIT_REPO} "
        "(the kit stays the source of truth), then tag the kit and re-sync it."
    )


@router.get("", response_model=List[LearnedRuleOut])
async def list_rules(
    status_filter: Optional[RuleStatus] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The user's rules, newest first."""
    query = select(LearnedRule).where(LearnedRule.user_id == current_user.id)
    if status_filter:
        query = query.where(LearnedRule.status == status_filter)
    query = query.order_by(LearnedRule.created_at.desc(), LearnedRule.id)
    return (await db.execute(query)).scalars().all()


@router.post("/propose", response_model=LearnedRuleProposeOut)
@limiter.limit("10/hour")
async def propose(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Propose at most 5 rules from the user's edits and refine requests. Never auto-accepts."""
    try:
        rows, evidence = await propose_rules(db, current_user.id)
    except LLMError as exc:
        await db.rollback()
        return generation_unavailable(
            exc, status.HTTP_502_BAD_GATEWAY,
            "Suggesting rules is temporarily unavailable. Please try again shortly.",
        )
    await db.commit()
    return LearnedRuleProposeOut(
        proposed=[LearnedRuleOut.model_validate(r) for r in rows],
        pairs_found=len(evidence.pairs),
        refine_requests_found=len(evidence.refine_requests),
    )


@router.put("/{rule_id}", response_model=LearnedRuleDecisionOut)
async def decide_rule(
    rule_id: str,
    body: LearnedRuleDecision,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept or reject a proposed rule. A decision is final (append-only): 409 on a decided rule."""
    rule = (await db.execute(
        select(LearnedRule).where(LearnedRule.id == rule_id, LearnedRule.user_id == current_user.id)
        .with_for_update()
    )).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    if rule.status != "proposed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Rule already {rule.status}")
    rule.status = body.status
    rule.decided_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(rule)
    out = LearnedRuleDecisionOut.model_validate(rule)
    if body.status == "accepted":
        out.note = voice_kit_note(current_user.email)
    return out
