"""Job-queue drafts run on the v2 engine for generation_v2 users and stay traceable."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.api.v1 import job_queue
from app.models.cover_letter import CoverLetter
from app.models.job import Job
from app.models.job_queue import JobQueueItem
from app.models.user import UserProfile
from app.services.generation.brief import JobBrief
from tests.conftest import TestSessionLocal

URL = "https://www.upwork.com/jobs/~01inspectionplatform"


def _v2_result():
    brief = JobBrief(needs=["n"], job_types=[], client_signals={}, mirror_phrases=[], explicit_asks=[],
                     questions=[], title="Inspection platform", description="Maintain our app")
    return SimpleNamespace(
        draft=SimpleNamespace(cover_letter="Inspection software earns its keep in the field.\n\nRegards,",
                              fact_ids_used=["fact-1"], screening_answers=[]),
        brief=brief, evidence=SimpleNamespace(voice_samples=[]), warnings=[],
    )


async def _seed(db, user, v2: bool) -> str:
    db.add(UserProfile(user_id=user.id, generation_v2=v2))
    item = JobQueueItem(user_id=user.id, upwork_url=URL, title="Inspection platform",
                        description="Maintain our Flutter inspection app.", skills=["Flutter"],
                        draft_status="generating")
    db.add(item)
    await db.commit()
    return item.id


async def _run(item_id, user_id, v2_gen, legacy_gen):
    with patch("app.core.database.async_session_maker", TestSessionLocal), \
         patch("app.services.generation.generate_application", v2_gen), \
         patch("app.services.cover_letter.generate_cover_letter", legacy_gen), \
         patch("app.services.job_analysis.run_full_analysis", AsyncMock(return_value=SimpleNamespace(
             skill_matches=[], missing_skills=[], relevant_memories=[]))), \
         patch("app.services.job_analysis.find_relevant_proposals", AsyncMock(return_value=[])), \
         patch.object(job_queue, "_record_outcome", AsyncMock()), \
         patch.object(job_queue, "record_proposal_drafted", AsyncMock()):
        await job_queue._generate_draft_background(item_id=item_id, user_id=user_id)


@pytest.mark.asyncio
async def test_v2_user_queue_draft_uses_the_v2_engine_and_keeps_a_traceable_letter(db_session, test_user):
    item_id = await _seed(db_session, test_user, v2=True)
    v2_gen, legacy_gen = AsyncMock(return_value=_v2_result()), AsyncMock(return_value="legacy")
    await _run(item_id, test_user.id, v2_gen, legacy_gen)

    legacy_gen.assert_not_awaited()
    v2_gen.assert_awaited_once()
    async with TestSessionLocal() as db:
        item = (await db.execute(select(JobQueueItem).where(JobQueueItem.id == item_id))).scalar_one()
        assert item.draft_status == "ready" and item.draft_cover_letter.startswith("Inspection software")
        job = (await db.execute(select(Job).where(Job.upwork_url == URL))).scalar_one()
        letter = (await db.execute(select(CoverLetter).where(CoverLetter.job_id == job.id))).scalar_one()
        assert letter.prompt_version == "v2" and letter.fact_ids_used == ["fact-1"]

        # The edited text the user sends is recorded on that letter, so outcomes credit its facts.
        await job_queue._mark_v2_letter_sent(db, item, "Final text as sent.")
        await db.commit()
        letter = (await db.execute(select(CoverLetter).where(CoverLetter.id == letter.id))).scalar_one()
        assert letter.final_text == "Final text as sent." and letter.was_submitted is True


@pytest.mark.asyncio
async def test_second_draft_reuses_the_job_row(db_session, test_user):
    item_id = await _seed(db_session, test_user, v2=True)
    for _ in range(2):
        await _run(item_id, test_user.id, AsyncMock(return_value=_v2_result()), AsyncMock())
    async with TestSessionLocal() as db:
        jobs = (await db.execute(select(Job).where(Job.upwork_url == URL))).scalars().all()
        letters = (await db.execute(select(CoverLetter))).scalars().all()
    assert len(jobs) == 1 and len(letters) == 2


@pytest.mark.asyncio
async def test_flag_off_user_keeps_the_legacy_draft(db_session, test_user):
    item_id = await _seed(db_session, test_user, v2=False)
    v2_gen, legacy_gen = AsyncMock(), AsyncMock(return_value="Legacy draft body")
    await _run(item_id, test_user.id, v2_gen, legacy_gen)
    v2_gen.assert_not_awaited()
    async with TestSessionLocal() as db:
        item = (await db.execute(select(JobQueueItem).where(JobQueueItem.id == item_id))).scalar_one()
        assert item.draft_cover_letter == "Legacy draft body"
        assert (await db.execute(select(CoverLetter))).scalars().all() == []
