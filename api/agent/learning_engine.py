"""LearningEngine — outcome signals improve future agent behavior.

Three learning mechanisms:

1. WINNING PROPOSAL → MEMORY
   When a user is hired, the cover letter that won is added to their proposal
   corpus as a high-importance memory (importance=0.95). This improves future
   cover letter generation for this user.

2. CROSS-USER SIGNAL CONTRIBUTION
   When an outcome is recorded (submitted/viewed/responded/hired/declined),
   an anonymized signal is contributed to the global_signal_pool. Only:
     - SHA-256 hash of sorted skill names (no text, no user_id)
     - outcome code
     - score at submission (float)
     - edit distance pct (float)
   This enables cold-start calibration for new users with similar skill profiles.

3. COLD-START INITIALIZATION
   When a new user_autonomy_profile is created, this module queries the
   global_signal_pool for similar skill hashes and initializes:
     - score_threshold from median of successful (hired/responded) scores
     - avg_edit_distance from median edit_distance_pct of similar users
"""
import hashlib
import logging
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.global_signal_pool import GlobalSignalPool
from app.models.memory import Memory
from app.models.user_autonomy_profile import UserAutonomyProfile
from app.core.embeddings import generate_embedding

logger = logging.getLogger(__name__)

# Outcome codes that count as "positive" for cold-start calibration
POSITIVE_OUTCOMES = {"responded", "invited", "hired"}


# ── Skill hash ───────────────────────────────────────────────────────────────

def compute_skill_hash(skills: list[str]) -> str:
    """Return SHA-256 of sorted, lowercased skill names.

    This is the anonymization key — two users with the same skill set
    share a hash but cannot be linked to each other or to any text.
    """
    normalized = sorted(s.strip().lower() for s in skills if s.strip())
    canonical = ",".join(normalized)
    return hashlib.sha256(canonical.encode()).hexdigest()


# ── Mechanism 1: Winning proposal → memory ────────────────────────────────────

async def winning_proposal_to_memory(
    user_id: str,
    job_title: str,
    job_description: str,
    cover_letter_text: str,
    db: AsyncSession,
) -> None:
    """Add a winning (hired) cover letter to the user's proposal corpus.

    Stored with importance=0.95 so it always surfaces in the top-N semantic
    search used during cover letter generation.
    """
    combined = (
        f"JOB: {job_title}\n\n"
        f"DESCRIPTION: {job_description[:500]}\n\n"
        f"WINNING COVER LETTER:\n{cover_letter_text}"
    )

    try:
        embedding = await generate_embedding(combined)
    except Exception as exc:
        logger.warning("Could not embed winning proposal for user %s: %s", user_id, exc)
        return

    memory = Memory(
        id=str(uuid4()),
        user_id=user_id,
        content=combined,
        memory_type="proposal",
        importance=0.95,
        embedding=embedding,
        metadata={"source": "agent_won", "job_title": job_title},
    )
    db.add(memory)
    await db.flush()
    logger.info(
        "Added winning proposal memory for user %s (job: %s)", user_id, job_title[:50]
    )


# ── Mechanism 2: Cross-user signal contribution ───────────────────────────────

async def contribute_signal(
    skills: list[str],
    outcome_code: str,
    score_at_submission: Optional[float],
    edit_distance_pct: Optional[float],
    db: AsyncSession,
) -> None:
    """Contribute one anonymized signal to the global_signal_pool."""
    if not skills:
        return

    skill_hash = compute_skill_hash(skills)
    signal = GlobalSignalPool(
        id=str(uuid4()),
        skill_hash=skill_hash,
        outcome_code=outcome_code,
        score_at_submission=score_at_submission,
        edit_distance_pct=edit_distance_pct,
    )
    db.add(signal)
    await db.flush()
    logger.debug(
        "Signal contributed: hash=%s outcome=%s score=%s",
        skill_hash[:8], outcome_code, score_at_submission,
    )


# ── Mechanism 3: Cold-start initialization ────────────────────────────────────

async def initialize_from_pool(
    user_id: str,
    skills: list[str],
    db: AsyncSession,
    min_signals: int = 5,
) -> dict:
    """Initialize a new user's autonomy profile thresholds from the global pool.

    Returns a dict of suggested values (caller decides whether to apply them).
    Returns empty dict if the pool has too few signals for this skill hash.
    """
    if not skills:
        return {}

    skill_hash = compute_skill_hash(skills)

    # Fetch all signals for this skill hash
    result = await db.execute(
        select(GlobalSignalPool).where(GlobalSignalPool.skill_hash == skill_hash)
    )
    signals = result.scalars().all()

    if len(signals) < min_signals:
        logger.info(
            "Cold-start: only %d signals for skill_hash %s — using defaults",
            len(signals), skill_hash[:8],
        )
        return {}

    # Median score of positive outcomes → suggested score_threshold
    positive_scores = [
        s.score_at_submission for s in signals
        if s.outcome_code in POSITIVE_OUTCOMES and s.score_at_submission is not None
    ]
    all_scores = [
        s.score_at_submission for s in signals
        if s.score_at_submission is not None
    ]

    # Median edit distance across all signals
    edit_distances = [
        s.edit_distance_pct for s in signals
        if s.edit_distance_pct is not None
    ]

    suggestions: dict = {}

    if positive_scores:
        sorted_pos = sorted(positive_scores)
        median_pos = sorted_pos[len(sorted_pos) // 2]
        # Set threshold at the 40th percentile of winning scores (inclusive bias)
        suggestions["score_threshold"] = round(max(40.0, median_pos * 0.85), 1)

    if edit_distances:
        sorted_ed = sorted(edit_distances)
        median_ed = sorted_ed[len(sorted_ed) // 2]
        suggestions["avg_edit_distance"] = round(median_ed, 4)

    if all_scores:
        response_rate = len(positive_scores) / len(signals)
        suggestions["estimated_response_rate"] = round(response_rate, 3)

    logger.info(
        "Cold-start suggestions for user %s (skill_hash=%s, n=%d signals): %s",
        user_id, skill_hash[:8], len(signals), suggestions,
    )
    return suggestions


async def apply_cold_start(
    user_id: str,
    skills: list[str],
    db: AsyncSession,
) -> bool:
    """Apply cold-start suggestions to the user's autonomy profile.

    Only runs if the profile has never been evaluated (last_evaluated is None).
    Returns True if suggestions were applied.
    """
    ap_result = await db.execute(
        select(UserAutonomyProfile).where(UserAutonomyProfile.user_id == user_id)
    )
    ap = ap_result.scalar_one_or_none()

    if ap is None or ap.last_evaluated is not None:
        return False  # Profile already calibrated

    suggestions = await initialize_from_pool(user_id, skills, db)
    if not suggestions:
        return False

    if "score_threshold" in suggestions:
        ap.score_threshold = suggestions["score_threshold"]
    if "avg_edit_distance" in suggestions:
        ap.avg_edit_distance = suggestions["avg_edit_distance"]

    await db.flush()
    logger.info(
        "Cold-start applied for user %s: threshold=%.1f",
        user_id, ap.score_threshold,
    )
    return True
