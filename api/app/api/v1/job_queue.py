"""Job queue endpoints — agent-discovered jobs awaiting user review.

Routes:
  POST   /api/v1/job-queue                    — add a job (agent or manual)
  GET    /api/v1/job-queue/stats              — learning summary (last 30 decisions)
  GET    /api/v1/job-queue                    — list queued jobs for current user
  PUT    /api/v1/job-queue/{id}/action        — approve or reject a queued job
  POST   /api/v1/job-queue/{id}/draft         — generate cover letter draft
  POST   /api/v1/job-queue/{id}/submit-edit   — record final text + compute edit distance
  POST   /api/v1/job-queue/{id}/confirm-submit — user confirmed auto-fill, record bid/connects
  POST   /api/v1/job-queue/{id}/proposal-response — background script reports status change
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.job_queue import JobQueueItem
from app.models.outcome_event import OutcomeEvent
from app.models.user import User, UserProfile
from app.schemas.job_queue import (
    ConfirmSubmitRequest,
    ConfirmSubmitResponse,
    DraftSubmitRequest,
    DraftSubmitResponse,
    JobQueueActionRequest,
    JobQueueCreate,
    JobQueueItemResponse,
    ProposalResponseRequest,
)
from agent.autonomy_governor import (
    get_or_create_autonomy_profile,
    record_proposal_drafted,
    record_proposal_responded,
    record_suggestion_approved,
    record_suggestion_rejected,
    update_avg_edit_distance,
)
from agent.learning_engine import contribute_signal, winning_proposal_to_memory

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_STATUSES = {"suggested", "approved", "rejected", "applied", "expired"}
VALID_ACTIONS = {"approve", "reject"}


def _to_response(item: JobQueueItem) -> JobQueueItemResponse:
    return JobQueueItemResponse.model_validate(item)


async def _record_outcome(
    db: AsyncSession,
    user_id: str,
    job_queue_id: str,
    event_type: str,
    meta: Optional[dict] = None,
) -> None:
    """Insert one row into outcome_events."""
    event = OutcomeEvent(
        id=str(uuid4()),
        user_id=user_id,
        job_queue_id=job_queue_id,
        event_type=event_type,
        meta=meta,
    )
    db.add(event)
    await db.flush()


async def _get_user_profile(user_id: str, db: AsyncSession) -> Optional[UserProfile]:
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


# ── POST /api/v1/job-queue ─────────────────────────────────────────────────

@router.post("", response_model=JobQueueItemResponse, status_code=status.HTTP_201_CREATED)
async def create_job_queue_item(
    data: JobQueueCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a discovered job to the user's suggestion queue.

    Deduplicates by (user_id, upwork_url) — returns the existing item if the
    job is already in the queue.
    """
    result = await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.user_id == current_user.id,
            JobQueueItem.upwork_url == data.upwork_url,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return _to_response(existing)

    item = JobQueueItem(
        id=str(uuid4()),
        user_id=current_user.id,
        upwork_url=data.upwork_url,
        title=data.title,
        description=data.description,
        skills=data.skills or [],
        budget_amount=data.budget_amount,
        budget_type=data.budget_type,
        client_info=data.client_info,
        ai_score=data.ai_score,
        ai_reasoning=data.ai_reasoning,
        chips=data.chips or [],
        status="suggested",
        source=data.source,
        source_query_id=data.source_query_id,
        draft_status="none",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)

    await _record_outcome(db, current_user.id, item.id, "suggested")
    ap = await get_or_create_autonomy_profile(current_user.id, db)
    ap.suggestions_shown += 1
    await db.flush()

    logger.info(
        "Added job_queue item %s for user %s (score=%.1f)",
        item.id, current_user.id, item.ai_score or 0,
    )
    return _to_response(item)


# ── GET /api/v1/job-queue/stats ────────────────────────────────────────────
# Declared BEFORE /{item_id}/... routes to avoid path collision.

@router.get("/stats", response_model=Dict[str, Any])
async def get_queue_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a learning summary: autonomy level, approval rate, top rejection reasons."""
    ap = await get_or_create_autonomy_profile(current_user.id, db)

    recent_result = await db.execute(
        select(JobQueueItem)
        .where(
            JobQueueItem.user_id == current_user.id,
            JobQueueItem.status.in_(["approved", "rejected"]),
        )
        .order_by(JobQueueItem.reviewed_at.desc())
        .limit(30)
    )
    recent_items = recent_result.scalars().all()
    recent_approved = sum(1 for i in recent_items if i.status == "approved")
    recent_total = len(recent_items)
    recent_rate = (recent_approved / recent_total) if recent_total > 0 else None

    reasons_result = await db.execute(
        select(JobQueueItem.rejection_reason, func.count().label("cnt"))
        .where(
            JobQueueItem.user_id == current_user.id,
            JobQueueItem.status == "rejected",
            JobQueueItem.rejection_reason.isnot(None),
        )
        .group_by(JobQueueItem.rejection_reason)
        .order_by(func.count().desc())
        .limit(5)
    )
    top_reasons = [{"reason": r, "count": c} for r, c in reasons_result.fetchall()]

    level_labels = {
        1: "Observer", 2: "Suggester", 3: "Drafter",
        4: "Assisted", 5: "Autonomous", 6: "Optimizing",
    }

    return {
        "autonomy_level": ap.level,
        "autonomy_label": level_labels.get(ap.level, f"Level {ap.level}"),
        "level_since": ap.level_since.isoformat() if ap.level_since else None,
        "score_threshold": ap.score_threshold,
        "avg_edit_distance": ap.avg_edit_distance,
        "all_time": {
            "suggestions_shown": ap.suggestions_shown,
            "suggestions_approved": ap.suggestions_approved,
            "proposals_submitted": ap.proposals_submitted,
            "approval_rate": round(ap.approval_rate, 3),
        },
        "recent_30": {
            "total": recent_total,
            "approved": recent_approved,
            "approval_rate": round(recent_rate, 3) if recent_rate is not None else None,
        },
        "top_rejection_reasons": top_reasons,
    }


# ── GET /api/v1/job-queue ──────────────────────────────────────────────────

@router.get("", response_model=List[JobQueueItemResponse])
async def list_job_queue(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's job queue, newest first."""
    stmt = (
        select(JobQueueItem)
        .where(JobQueueItem.user_id == current_user.id)
        .order_by(JobQueueItem.created_at.desc())
        .limit(limit)
    )

    if status_filter:
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        invalid = set(statuses) - VALID_STATUSES
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status values: {invalid}. Valid: {VALID_STATUSES}",
            )
        stmt = stmt.where(JobQueueItem.status.in_(statuses))

    result = await db.execute(stmt)
    items = result.scalars().all()
    return [_to_response(item) for item in items]


# ── PUT /api/v1/job-queue/{id}/action ─────────────────────────────────────

@router.put("/{item_id}/action", response_model=JobQueueItemResponse)
async def action_job_queue_item(
    item_id: str,
    body: JobQueueActionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a queued job.

    At Level 3+, approving a job automatically triggers background draft generation.
    """
    if body.action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid action '{body.action}'. Valid: {VALID_ACTIONS}",
        )

    result = await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.id == item_id,
            JobQueueItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found.")

    if body.action == "approve":
        item.status = "approved"
        await _record_outcome(db, current_user.id, item_id, "approved")
        level_change = await record_suggestion_approved(current_user.id, db)

        # At Level 3+, auto-queue draft generation
        if level_change["level_after"] >= 3:
            item.draft_status = "generating"
            await db.flush()
            background_tasks.add_task(
                _generate_draft_background,
                item_id=item_id,
                user_id=current_user.id,
            )
    else:
        item.status = "rejected"
        item.rejection_reason = body.rejection_reason
        meta = {"rejection_reason": body.rejection_reason} if body.rejection_reason else None
        await _record_outcome(db, current_user.id, item_id, "rejected", meta)
        level_change = await record_suggestion_rejected(current_user.id, db)

    item.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(item)

    if level_change["level_before"] != level_change["level_after"]:
        logger.info(
            "User %s autonomy: Level %d → %d",
            current_user.id, level_change["level_before"], level_change["level_after"],
        )

    logger.info(
        "Job queue item %s → %s by user %s (threshold=%.1f)",
        item_id, item.status, current_user.id, level_change["threshold_after"],
    )
    return _to_response(item)


# ── POST /api/v1/job-queue/{id}/draft ─────────────────────────────────────

@router.post("/{item_id}/draft", response_model=JobQueueItemResponse)
async def generate_queue_item_draft(
    item_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger cover letter draft generation for an approved queue item.

    Returns immediately with draft_status="generating".
    The draft is written asynchronously; poll GET /api/v1/job-queue to check status.
    """
    result = await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.id == item_id,
            JobQueueItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found.")

    if item.status not in ("approved", "suggested"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot generate draft for item with status '{item.status}'.",
        )

    if item.draft_status == "generating":
        return _to_response(item)  # Already in progress

    item.draft_status = "generating"
    await db.flush()
    await db.refresh(item)

    background_tasks.add_task(
        _generate_draft_background,
        item_id=item_id,
        user_id=current_user.id,
    )

    return _to_response(item)


async def _generate_draft_background(item_id: str, user_id: str) -> None:
    """Background task: generate cover letter draft and persist it."""
    from app.core.database import async_session_maker as AsyncSessionLocal
    from app.services.cover_letter import generate_cover_letter
    from app.services.job_analysis import (
        run_full_analysis,
        find_relevant_proposals,
    )

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(JobQueueItem).where(JobQueueItem.id == item_id)
            )
            item = result.scalar_one_or_none()
            if item is None:
                return

            profile = await _get_user_profile(user_id, db)
            if profile is None:
                logger.warning("No profile for user %s — cannot generate draft", user_id)
                item.draft_status = "none"
                await db.commit()
                return

            # Run lightweight analysis to get skill matches + memories
            ar = await run_full_analysis(
                title=item.title,
                description=item.description or "",
                skills=item.skills or [],
                budget=item.budget_amount,
                client_info=item.client_info,
                profile=profile,
                db=db,
            )

            past_proposals = await find_relevant_proposals(
                db=db,
                user_id=user_id,
                job_description=item.description or "",
                job_skills=item.skills or [],
                limit=3,
                successful_only=False,
            )

            draft = await generate_cover_letter(
                job_title=item.title,
                job_description=item.description or "",
                job_skills=item.skills or [],
                budget=item.budget_amount,
                skill_matches=ar.skill_matches,
                missing_skills=ar.missing_skills,
                relevant_memories=ar.relevant_memories,
                profile=profile,
                past_proposals=past_proposals,
            )

            item.draft_cover_letter = draft
            item.draft_status = "ready"
            item.draft_generated_at = datetime.now(timezone.utc)

            # Record outcome event
            await _record_outcome(db, user_id, item_id, "proposal_drafted")
            await record_proposal_drafted(user_id, db)

            await db.commit()
            logger.info("Draft generated for queue item %s (user %s)", item_id, user_id)

        except Exception as exc:
            logger.error("Draft generation failed for item %s: %s", item_id, exc)
            try:
                result = await db.execute(
                    select(JobQueueItem).where(JobQueueItem.id == item_id)
                )
                item = result.scalar_one_or_none()
                if item:
                    item.draft_status = "none"
                    await db.commit()
            except Exception:
                pass


# ── POST /api/v1/job-queue/{id}/submit-edit ────────────────────────────────

@router.post("/{item_id}/submit-edit", response_model=DraftSubmitResponse)
async def submit_edit(
    item_id: str,
    body: DraftSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record the final cover letter text the user sent.

    Computes word-level edit distance vs. the stored AI draft.
    Updates avg_edit_distance on user_autonomy_profiles.
    Marks draft_status = "sent".
    """
    from app.services.edit_distance import word_edit_distance_pct

    result = await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.id == item_id,
            JobQueueItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found.")

    if not item.draft_cover_letter:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No draft available for this queue item.",
        )

    dist = word_edit_distance_pct(item.draft_cover_letter, body.final_text)

    # Record outcome event with distance
    meta = {
        "edit_distance_pct": dist,
        "auto_filled": body.auto_filled,
        "word_count_original": len(item.draft_cover_letter.split()),
        "word_count_final": len(body.final_text.split()),
    }
    await _record_outcome(db, current_user.id, item_id, "proposal_submitted", meta)

    # Update rolling avg and re-evaluate level
    level_change = await update_avg_edit_distance(current_user.id, dist, db)

    item.draft_status = "sent"
    item.status = "applied"
    await db.flush()

    # Contribute anonymized signal for this submission
    item_skills = item.skills or []
    if item_skills:
        try:
            await contribute_signal(
                skills=item_skills,
                outcome_code="submitted",
                score_at_submission=item.ai_score,
                edit_distance_pct=dist,
                db=db,
            )
        except Exception as exc:
            logger.warning("Signal contribution failed on submit-edit: %s", exc)

    ap_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    # Re-fetch updated avg
    from app.models.user_autonomy_profile import UserAutonomyProfile
    ap_q = await db.execute(
        select(UserAutonomyProfile).where(UserAutonomyProfile.user_id == current_user.id)
    )
    ap = ap_q.scalar_one_or_none()

    pct_str = f"{dist * 100:.1f}%"
    if dist <= 0.05:
        msg = f"Minimal edits ({pct_str}) — the agent is learning your voice well."
    elif dist <= 0.20:
        msg = f"Light edits ({pct_str}) — good calibration signal recorded."
    else:
        msg = f"Significant edits ({pct_str}) — agent will adjust its style."

    logger.info(
        "Submit-edit for item %s: edit_distance=%.1f%% (user %s, level %d → %d)",
        item_id, dist * 100, current_user.id,
        level_change["level_before"], level_change["level_after"],
    )

    return DraftSubmitResponse(
        edit_distance_pct=dist,
        avg_edit_distance=ap.avg_edit_distance if ap else None,
        message=msg,
    )

# ── POST /api/v1/job-queue/{id}/confirm-submit ─────────────────────────────

@router.post("/{item_id}/confirm-submit", response_model=ConfirmSubmitResponse)
async def confirm_submit(
    item_id: str,
    body: ConfirmSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record the user's confirmation to auto-fill and submit a proposal.

    Called immediately before the extension opens the apply tab.
    Stores bid_amount, connects_spent, and sets confirmed_at.
    The extension then writes pendingAutoFill to chrome.storage and opens the tab.
    """
    result = await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.id == item_id,
            JobQueueItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found.")

    if item.draft_status not in ("ready", "sent"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Draft must be ready before confirming submission.",
        )

    item.bid_amount = body.bid_amount
    item.connects_spent = body.connects_spent
    item.confirmed_at = datetime.now(timezone.utc)
    if body.upwork_proposal_id:
        item.upwork_proposal_id = body.upwork_proposal_id

    meta = {
        "bid_amount": float(body.bid_amount) if body.bid_amount else None,
        "connects_spent": body.connects_spent,
    }
    await _record_outcome(db, current_user.id, item_id, "confirmed_submit", meta)
    await db.flush()

    ap = await get_or_create_autonomy_profile(current_user.id, db)
    logger.info(
        "Confirmed submission for queue item %s (user %s, level %d)",
        item_id, current_user.id, ap.level,
    )

    return ConfirmSubmitResponse(
        status="confirmed",
        message="Auto-fill confirmed. Opening apply page now.",
        autonomy_level=ap.level,
    )


# ── POST /api/v1/job-queue/{id}/proposal-response ──────────────────────────

VALID_RESPONSE_TYPES = {"viewed", "responded", "invited", "declined"}


@router.post("/{item_id}/proposal-response", response_model=JobQueueItemResponse)
async def record_proposal_response(
    item_id: str,
    body: ProposalResponseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a client action on a submitted proposal.

    Called by the background script when it detects a proposal status change
    on the Upwork proposals page. Also used to record the Upwork proposal ID
    once it's known (on the first call after submission).

    response_type: viewed | responded | invited | declined
    """
    if body.response_type not in VALID_RESPONSE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid response_type '{body.response_type}'. Valid: {VALID_RESPONSE_TYPES}",
        )

    result = await db.execute(
        select(JobQueueItem).where(
            JobQueueItem.id == item_id,
            JobQueueItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found.")

    # Only upgrade client_response_type (don't downgrade responded → viewed)
    RESPONSE_RANK = {"viewed": 1, "responded": 2, "invited": 3, "declined": 0}
    current_rank = RESPONSE_RANK.get(item.client_response_type or "", -1)
    new_rank = RESPONSE_RANK.get(body.response_type, 0)

    if new_rank > current_rank:
        item.client_response_type = body.response_type
        item.client_response_at = datetime.now(timezone.utc)

    if body.upwork_proposal_id and not item.upwork_proposal_id:
        item.upwork_proposal_id = body.upwork_proposal_id

    item.last_status_check = datetime.now(timezone.utc)

    # Record outcome event
    await _record_outcome(
        db, current_user.id, item_id, body.response_type,
        meta={"upwork_proposal_id": body.upwork_proposal_id},
    )

    # For responded/invited → increment proposals_responded on autonomy profile
    if body.response_type in ("responded", "invited"):
        level_change = await record_proposal_responded(current_user.id, db)
        if level_change["level_before"] != level_change["level_after"]:
            logger.info(
                "User %s: autonomy level %d → %d (response signal)",
                current_user.id, level_change["level_before"], level_change["level_after"],
            )

    # Contribute anonymized signal to global pool
    item_skills = item.skills or []
    if item_skills:
        ap = await get_or_create_autonomy_profile(current_user.id, db)
        try:
            await contribute_signal(
                skills=item_skills,
                outcome_code=body.response_type,
                score_at_submission=item.ai_score,
                edit_distance_pct=ap.avg_edit_distance,
                db=db,
            )
        except Exception as exc:
            logger.warning("Signal contribution failed for item %s: %s", item_id, exc)

    # If hired: add winning cover letter to memory corpus
    if body.response_type == "invited" and item.draft_cover_letter:
        try:
            await winning_proposal_to_memory(
                user_id=current_user.id,
                job_title=item.title,
                job_description=item.description or "",
                cover_letter_text=item.draft_cover_letter,
                db=db,
            )
        except Exception as exc:
            logger.warning("winning_proposal_to_memory failed for item %s: %s", item_id, exc)

    await db.flush()
    await db.refresh(item)
    logger.info(
        "Proposal response '%s' for item %s (user %s)",
        body.response_type, item_id, current_user.id,
    )
    return _to_response(item)
