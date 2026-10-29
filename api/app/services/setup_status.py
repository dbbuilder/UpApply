"""Is a user set up for memory-driven generation (v2)? A read-only checklist (career-ops idea 8):
enough approved facts to ground letters, at least one of the user's own letters as a voice
sample, and the profile basics the writer prompt uses."""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fact import Fact
from app.models.proposal import Proposal
from app.models.user import UserProfile
from app.services.generation.evidence import VOICE_AUTHORS

MIN_APPROVED_FACTS = 25
MIN_VOICE_SAMPLES = 1


async def setup_status(db: AsyncSession, user_id: str, profile: Optional[UserProfile]) -> dict:
    approved = (await db.execute(
        select(func.count()).select_from(Fact).where(Fact.user_id == user_id, Fact.status == "approved")
    )).scalar_one()
    # Same filter evidence._find_voice_samples uses, so this counts what can reach the writer.
    voice = (await db.execute(
        select(func.count()).select_from(Proposal).where(
            Proposal.user_id == user_id,
            Proposal.author.in_(VOICE_AUTHORS),
            Proposal.job_needs_embedding.isnot(None),
            func.length(func.trim(Proposal.cover_letter_text)) > 0,
        )
    )).scalar_one()
    basics = bool(profile and (profile.full_name or "").strip() and (profile.professional_title or "").strip())
    missing = []
    if approved < MIN_APPROVED_FACTS:
        missing.append(f"approved facts: {approved} of {MIN_APPROVED_FACTS}")
    if voice < MIN_VOICE_SAMPLES:
        missing.append(
            "a past proposal you wrote or edited (voice sample): import your Upwork proposals in the "
            "extension, or run POST /api/v1/proposals/backfill-job-embeddings for proposals already saved"
        )
    if not basics:
        missing.append("profile name and professional title")
    return {
        "ready": not missing,
        "approved_facts": approved,
        "voice_samples": voice,
        "has_profile_basics": basics,
        "missing": missing,
    }
