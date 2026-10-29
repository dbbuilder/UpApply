"""Imported proposals: an UpApply draft sent unchanged is 'ai', never a voice sample."""
import pytest

from app.api.v1.proposals import _server_author
from app.models.cover_letter import CoverLetter
from app.models.job import Job

URL = "https://www.upwork.com/jobs/~01abcdef"
DRAFT = "Inspection software earns its keep in the field, where inspectors work offline and sync later."


async def _seed_draft(db, user):
    job = Job(user_id=user.id, upwork_url=URL, title="Inspection platform", description="d")
    db.add(job)
    await db.flush()
    db.add(CoverLetter(user_id=user.id, job_id=job.id, content=DRAFT, model_used="m", version=1))
    await db.commit()


@pytest.mark.asyncio
async def test_unchanged_draft_is_ai(db_session, test_user):
    await _seed_draft(db_session, test_user)
    assert await _server_author(db_session, test_user.id, URL, "Inspection platform", DRAFT) == "ai"


@pytest.mark.asyncio
async def test_edited_draft_is_a_voice_sample(db_session, test_user):
    await _seed_draft(db_session, test_user)
    edited = "Field inspection apps are judged offline. I rebuilt one for hospitals and kept sync simple."
    assert await _server_author(db_session, test_user.id, URL, "Inspection platform", edited) == "chris_edited_ai"


@pytest.mark.asyncio
async def test_no_upapply_draft_means_user_written(db_session, test_user):
    assert await _server_author(db_session, test_user.id, URL, "Inspection platform", DRAFT) == "chris"
