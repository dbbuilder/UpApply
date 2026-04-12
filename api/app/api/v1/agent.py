"""Agent status endpoints.

Routes:
  GET /api/v1/agent/digest     — daily digest (activity, pipeline, ROI)
  GET /api/v1/agent/roi        — ROI summary (connects invested vs. responses)
  GET /api/v1/agent/optimize   — Level 6 query improvement suggestions
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from agent.digest import build_digest
from agent.autonomy_governor import get_or_create_autonomy_profile
from agent.search_optimizer import suggest_query_improvements

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/digest")
async def get_digest(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the full daily digest for the current user.

    Includes autonomy level, today's activity, pipeline state, learning metrics,
    ROI data, and recent activity feed.
    """
    digest = await build_digest(current_user.id, db)
    if "error" in digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=digest["error"],
        )
    return digest


@router.get("/roi")
async def get_roi(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a focused ROI summary (connects → responses → value).

    A subset of /digest focused on economic efficiency metrics.
    """
    digest = await build_digest(current_user.id, db)
    if "error" in digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=digest["error"],
        )
    return {
        "autonomy_level": digest["autonomy"]["level"],
        "autonomy_label": digest["autonomy"]["label"],
        "learning": digest["learning"],
        "roi_30d": digest["roi_30d"],
        "pipeline": digest["pipeline"],
    }


@router.get("/optimize")
async def get_optimize_suggestions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return search query improvement suggestions (Level 6 feature).

    Analyzes winning job patterns and suggests new queries or keyword additions
    not currently covered by the user's active search queries.

    Available at any level, but only meaningfully populated at Level 5+.
    """
    ap = await get_or_create_autonomy_profile(current_user.id, db)
    suggestions = await suggest_query_improvements(current_user.id, db)

    return {
        "autonomy_level": ap.level,
        "suggestions": suggestions,
        "note": (
            "These are suggestions only — apply them manually in Search Settings."
            if suggestions else
            "No suggestions yet — submit more proposals to build pattern data."
        ),
    }
