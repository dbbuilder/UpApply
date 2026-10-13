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
