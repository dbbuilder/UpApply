"""Guardrail config endpoints.

Routes:
  GET  /api/v1/guardrails   — get current user's guardrail config
  PUT  /api/v1/guardrails   — update (PATCH semantics, all fields optional)
  GET  /api/v1/guardrails/check — run preflight check without submitting
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.guardrail import GuardrailConfigResponse, GuardrailConfigUpdate
from agent.guardrails import (
    get_or_create_guardrails,
    check_submission_guards,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=GuardrailConfigResponse)
async def get_guardrails(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's guardrail configuration.

    Creates a default config if one does not yet exist.
    """
    cfg = await get_or_create_guardrails(current_user.id, db)
    await db.commit()
    return GuardrailConfigResponse.model_validate(cfg)


@router.put("", response_model=GuardrailConfigResponse)
async def update_guardrails(
    body: GuardrailConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the user's guardrail config (PATCH semantics).

    Only supplied fields are modified. Returns the updated config.
    """
    cfg = await get_or_create_guardrails(current_user.id, db)

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(cfg, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(cfg)

    logger.info(
        "Guardrail config updated for user %s: %s",
        current_user.id, list(update_data.keys()),
    )
    return GuardrailConfigResponse.model_validate(cfg)


@router.get("/check")
async def check_guardrails(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a preflight guardrail check without submitting anything.

    Returns whether submission is currently allowed and any active violations
    or warnings. Useful for the extension to show a status indicator.
    """
    result = await check_submission_guards(current_user.id, db)
    return {
        "passed": result.passed,
        "violations": [
            {"guard": v.guard, "reason": v.reason}
            for v in result.violations
        ],
        "warnings": result.warnings,
    }
