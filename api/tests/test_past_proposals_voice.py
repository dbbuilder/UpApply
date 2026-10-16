"""Regression: declined letters are never used or labelled as voice examples (phase 0)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.models.proposal import Proposal
from app.services.cover_letter import build_user_prompt, format_past_proposals
from app.services.job_analysis import find_relevant_proposals
from tests.conftest import TestSessionLocal


def test_format_past_proposals_excludes_declined_letters():
    text = format_past_proposals([
        {"was_hired": True, "job_title": "Won job", "cover_letter_text": "WON LETTER"},
        {"was_hired": False, "job_title": "Lost job", "cover_letter_text": "LOST LETTER"},
        {"was_hired": None, "job_title": "Pending job", "cover_letter_text": "PENDING LETTER"},
    ])
    assert "LOST LETTER" not in text
    assert "outcome unknown" not in text
    assert "Example 1 [WON — This letter got hired ✓] - For: Won job" in text
    assert "Example 2 [SUBMITTED — outcome pending] - For: Pending job" in text


def test_format_past_proposals_all_declined_returns_empty():
    assert format_past_proposals([
        {"was_hired": False, "cover_letter_text": "LOST LETTER"},
    ]) == ""


def test_build_user_prompt_omits_section_when_only_declined_letters():
    profile = MagicMock()
    profile.skills_to_highlight = None
    prompt = build_user_prompt(
        job_title="T",
        job_description="D",
        job_skills=[],
        budget=None,
        skill_matches=[],
        missing_skills=[],
        relevant_memories=[],
        profile=profile,
        past_proposals=[{"was_hired": False, "cover_letter_text": "LOST LETTER"}],
    )
    assert "PAST PROPOSALS" not in prompt
    assert "Learn from both" not in prompt


@pytest.mark.asyncio
async def test_find_relevant_proposals_skips_declined(
    client: AsyncClient, auth_headers: dict
):
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = me.json()["id"]
    vec = [0.1] * 1536
    async with TestSessionLocal() as session:
        session.add_all([
            Proposal(user_id=user_id, cover_letter_text="HIRED", was_hired=True, embedding=vec),
            Proposal(user_id=user_id, cover_letter_text="DECLINED", was_hired=False, embedding=vec),
            Proposal(user_id=user_id, cover_letter_text="PENDING", was_hired=None, embedding=vec),
        ])
        await session.commit()

    async with TestSessionLocal() as session:
        with patch("app.services.job_analysis.generate_embedding", AsyncMock(return_value=vec)):
            proposals = await find_relevant_proposals(
                db=session,
                user_id=user_id,
                job_description="anything",
                job_skills=[],
                limit=3,
            )

    texts = [p["cover_letter_text"] for p in proposals]
    assert texts == ["HIRED", "PENDING"]


def test_format_past_proposals_keeps_legacy_scraped_pending_letters():
    # Upwork imports before the importer fix stored pending letters as was_hired=False.
    text = format_past_proposals([
        {"was_hired": False, "status": "submitted", "job_title": "Pending A", "cover_letter_text": "SCRAPED PENDING"},
        {"was_hired": False, "status": "Interviewed", "job_title": "Pending B", "cover_letter_text": "SCRAPED INTERVIEW"},
        {"was_hired": False, "status": "declined", "cover_letter_text": "DECLINED LETTER"},
        {"was_hired": False, "status": "imported", "cover_letter_text": "CHATGPT LETTER"},
    ])
    assert "Example 1 [SUBMITTED — outcome pending] - For: Pending A" in text
    assert "Example 2 [SUBMITTED — outcome pending] - For: Pending B" in text
    assert "DECLINED LETTER" not in text
    assert "CHATGPT LETTER" not in text


@pytest.mark.asyncio
async def test_find_relevant_proposals_keeps_legacy_scraped_pending(
    client: AsyncClient, auth_headers: dict
):
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = me.json()["id"]
    vec = [0.1] * 1536
    async with TestSessionLocal() as session:
        session.add_all([
            Proposal(user_id=user_id, cover_letter_text="SCRAPED PENDING", was_hired=False,
                     status="submitted", source="scraped", embedding=vec),
            Proposal(user_id=user_id, cover_letter_text="SCRAPED DECLINED", was_hired=False,
                     status="declined", source="scraped", embedding=vec),
            Proposal(user_id=user_id, cover_letter_text="CHATGPT", was_hired=False,
                     status="imported", source="chatgpt_import", embedding=vec),
        ])
        await session.commit()

    async with TestSessionLocal() as session:
        with patch("app.services.job_analysis.generate_embedding", AsyncMock(return_value=vec)):
            proposals = await find_relevant_proposals(
                db=session,
                user_id=user_id,
                job_description="anything",
                job_skills=[],
                limit=5,
            )

    assert [p["cover_letter_text"] for p in proposals] == ["SCRAPED PENDING"]


@pytest.mark.asyncio
async def test_import_from_upwork_stores_pending_statuses_as_unknown_outcome(
    client: AsyncClient, auth_headers: dict
):
    scraped = [
        {"proposalId": f"p-{s}", "jobTitle": f"Job {s}", "coverLetter": f"Letter {s}", "status": s}
        for s in ("submitted", "active", "viewed", "responded", "interviewed", "hired", "declined", "archived")
    ]
    scraped.append({"proposalId": "p-default", "jobTitle": "Job default", "coverLetter": "Letter"})
    with patch("app.api.v1.proposals.generate_embedding", AsyncMock(return_value=[0.1] * 1536)):
        resp = await client.post(
            "/api/v1/proposals/import-from-upwork",
            json={"proposals": scraped},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    by_status = {p["upwork_proposal_id"]: p["was_hired"] for p in resp.json()}
    assert by_status == {
        "p-submitted": None,
        "p-active": None,
        "p-viewed": None,
        "p-responded": None,
        "p-interviewed": None,
        "p-hired": True,
        "p-declined": False,
        "p-archived": False,
        "p-default": None,
    }
