"""GET /api/v1/profile/setup-status and the setup checklist behind it."""
import pytest
from httpx import AsyncClient

from app.models.fact import Fact
from app.models.proposal import Proposal
from app.models.user import UserProfile
from app.services.setup_status import MIN_APPROVED_FACTS, setup_status


def _facts(user_id, n):
    return [Fact(user_id=user_id, kind="project", statement=f"Fact {i}", status="approved", source_type="manual")
            for i in range(n)]


def _voice_sample(user_id):
    return Proposal(user_id=user_id, cover_letter_text="A letter I wrote.", author="chris",
                    job_needs_embedding=[0.0] * 1535 + [1.0])


@pytest.mark.asyncio
async def test_brand_new_user_is_not_ready_and_sees_every_missing_item(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/profile/setup-status", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is False and data["approved_facts"] == 0 and data["voice_samples"] == 0
    assert len(data["missing"]) == 3


@pytest.mark.asyncio
async def test_setup_status_requires_auth(client: AsyncClient):
    assert (await client.get("/api/v1/profile/setup-status")).status_code == 401


@pytest.mark.asyncio
async def test_ready_user(db_session, test_user):
    profile = UserProfile(user_id=test_user.id, full_name="Gus Tello", professional_title="Engineer")
    db_session.add_all([profile, *_facts(test_user.id, MIN_APPROVED_FACTS), _voice_sample(test_user.id)])
    await db_session.commit()
    status = await setup_status(db_session, test_user.id, profile)
    assert status["ready"] is True and status["missing"] == []
    assert status["approved_facts"] == MIN_APPROVED_FACTS and status["voice_samples"] == 1


@pytest.mark.asyncio
async def test_facts_but_no_voice_samples(db_session, test_user):
    profile = UserProfile(user_id=test_user.id, full_name="Gus Tello", professional_title="Engineer")
    ai_only = Proposal(user_id=test_user.id, cover_letter_text="AI draft.", author="ai",
                       job_needs_embedding=[0.0] * 1535 + [1.0])
    candidate = Fact(user_id=test_user.id, kind="project", statement="Unreviewed", source_type="manual")
    db_session.add_all([profile, *_facts(test_user.id, MIN_APPROVED_FACTS), ai_only, candidate])
    await db_session.commit()
    status = await setup_status(db_session, test_user.id, profile)
    assert status["ready"] is False and status["voice_samples"] == 0
    assert status["approved_facts"] == MIN_APPROVED_FACTS  # candidates don't count
    assert status["missing"] == ["a past proposal you wrote or edited (voice sample)"]
