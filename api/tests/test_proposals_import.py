"""import-from-upwork captures full voice samples (letter + answers + job text + outcome)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.proposal import Proposal
from tests.conftest import TestSessionLocal
from tests.vector_utils import unit

URL = "/api/v1/proposals/import-from-upwork"


@pytest.fixture
def fake_embed():
    mock = AsyncMock(return_value=unit(3))
    with patch("app.api.v1.proposals.generate_embedding", mock):
        yield mock


async def _row(upwork_id: str) -> Proposal:
    async with TestSessionLocal() as s:
        return (await s.execute(select(Proposal).where(Proposal.upwork_proposal_id == upwork_id))).scalar_one()


@pytest.mark.asyncio
async def test_import_stores_answers_job_text_and_outcome(client: AsyncClient, auth_headers: dict, fake_embed):
    r = await client.post(URL, headers=auth_headers, json={"proposals": [{
        "proposalId": "111", "jobTitle": "Azure SQL migration", "coverLetter": "Full letter text",
        "status": "archived", "wasHired": True, "jobDescription": "Move our SQL estate to Azure",
        "screeningAnswers": [
            {"question": "Similar projects?", "answer": "160-server migration"},
            {"question": "Empty", "answer": "  "},
        ],
    }]})
    assert r.status_code == 200
    body = r.json()[0]
    assert body["author"] == "chris"
    assert body["outcome"] == "hired"
    assert body["job_text"] == "Move our SQL estate to Azure"
    assert body["screening_answers"] == [{"question": "Similar projects?", "answer": "160-server migration"}]

    row = await _row("111")
    assert row.job_needs_embedding is not None
    texts = [c.args[0] for c in fake_embed.await_args_list]
    assert "Azure SQL migration\n\nMove our SQL estate to Azure" in texts


@pytest.mark.asyncio
async def test_outcome_derivation_and_author_validation(client: AsyncClient, auth_headers: dict, fake_embed):
    r = await client.post(URL, headers=auth_headers, json={"proposals": [
        {"proposalId": "201", "jobTitle": "A", "coverLetter": "x", "status": "interviewed"},
        {"proposalId": "202", "jobTitle": "B", "coverLetter": "x", "status": "responded", "author": "chris_edited_ai"},
        {"proposalId": "203", "jobTitle": "C", "coverLetter": "x", "status": "submitted", "author": "robot"},
        {"proposalId": "204", "jobTitle": "D", "coverLetter": "x", "status": "submitted", "outcome": "declined"},
        {"proposalId": "205", "jobTitle": "E", "coverLetter": "x", "status": "viewed"},
    ]})
    by_id = {p["upwork_proposal_id"]: p for p in r.json()}
    assert by_id["201"]["outcome"] == "interviewed"
    assert by_id["202"]["outcome"] == "replied"
    assert by_id["202"]["author"] == "chris_edited_ai"
    assert by_id["203"]["author"] == "chris"
    assert by_id["203"]["outcome"] is None
    assert by_id["204"]["outcome"] == "declined"
    assert by_id["205"]["outcome"] == "viewed"  # matches migration 022 backfill
    # Phase 0: open statuses keep was_hired unknown, not declined
    assert by_id["201"]["was_hired"] is None
    assert by_id["203"]["was_hired"] is None


@pytest.mark.asyncio
async def test_reimport_backfills_existing_row(client: AsyncClient, auth_headers: dict, fake_embed):
    await client.post(URL, headers=auth_headers, json={"proposals": [
        {"proposalId": "301", "jobTitle": "Old", "coverLetter": "short", "status": "submitted"},
    ]})
    r = await client.post(URL, headers=auth_headers, json={"proposals": [{
        "proposalId": "301", "jobTitle": "Old", "coverLetter": "short letter, now complete",
        "status": "interviewed", "jobDescription": "Need a fractional CTO",
        "screeningAnswers": [{"question": "Q1", "answer": "A1"}],
    }]})
    assert r.json() == []  # nothing newly created

    row = await _row("301")
    assert row.cover_letter_text == "short letter, now complete"
    assert row.screening_answers == [{"question": "Q1", "answer": "A1"}]
    assert row.job_text == "Need a fractional CTO"
    assert row.outcome == "interviewed"
    assert row.job_needs_embedding is not None


@pytest.mark.asyncio
async def test_reimport_never_regresses_outcome(client: AsyncClient, auth_headers: dict, fake_embed):
    await client.post(URL, headers=auth_headers, json={"proposals": [
        {"proposalId": "501", "jobTitle": "Won", "coverLetter": "x", "status": "archived", "wasHired": True},
        {"proposalId": "502", "jobTitle": "Talked", "coverLetter": "x", "status": "interviewed"},
    ]})
    await client.post(URL, headers=auth_headers, json={"proposals": [
        {"proposalId": "501", "jobTitle": "Won", "coverLetter": "x", "status": "responded"},
        {"proposalId": "502", "jobTitle": "Talked", "coverLetter": "x", "status": "declined"},
    ]})
    assert (await _row("501")).outcome == "hired"
    assert (await _row("502")).outcome == "interviewed"

    await client.post(URL, headers=auth_headers, json={"proposals": [
        {"proposalId": "502", "jobTitle": "Talked", "coverLetter": "x", "outcome": "replied"},
    ]})
    assert (await _row("502")).outcome == "interviewed"


@pytest.mark.asyncio
async def test_import_caps_free_text_sizes(client: AsyncClient, auth_headers: dict, fake_embed):
    r = await client.post(URL, headers=auth_headers, json={"proposals": [{"jobTitle": "x"}] * 1001})
    assert r.status_code == 422

    r = await client.post(URL, headers=auth_headers, json={"proposals": [{
        "proposalId": "401", "jobTitle": "B" * 2_000, "coverLetter": "c" * 50_000,
        "jobDescription": "j" * 50_000,
        "screeningAnswers": [{"question": "q" * 9000, "answer": "a" * 9000}] * 60,
    }]})
    body = r.json()[0]
    assert len(body["job_text"]) == 20_000
    assert len(body["cover_letter_text"]) == 20_000
    assert len(body["job_title"]) == 500
    assert all(len(c.args[0]) <= 20_000 + 600 for c in fake_embed.await_args_list)
    assert len(body["screening_answers"]) == 50
    assert len(body["screening_answers"][0]["question"]) == 5_000
    assert len(body["screening_answers"][0]["answer"]) == 5_000
