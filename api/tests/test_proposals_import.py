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
    assert by_id["202"]["author"] == "chris"  # client-sent author is ignored (no UpApply draft)
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


@pytest.mark.asyncio
async def test_reimport_recomputes_job_embedding_when_job_text_arrives(client: AsyncClient, auth_headers: dict, fake_embed):
    """List page first (title only), detail page later: job<->job embedding must use the job text."""
    await client.post(URL, headers=auth_headers, json={"proposals": [
        {"proposalId": "601", "jobTitle": "Fractional CTO", "coverLetter": "short", "status": "submitted"},
    ]})
    fake_embed.reset_mock()
    fake_embed.return_value = unit(7)
    await client.post(URL, headers=auth_headers, json={"proposals": [{
        "proposalId": "601", "jobTitle": "Fractional CTO", "coverLetter": "short",
        "status": "submitted", "jobDescription": "Lead our 5-person team",
    }]})
    texts = [c.args[0] for c in fake_embed.await_args_list]
    assert "Fractional CTO\n\nLead our 5-person team" in texts
    row = await _row("601")
    assert list(row.job_needs_embedding) == pytest.approx(unit(7))


async def _second_user_headers(client: AsyncClient) -> dict:
    r = await client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_same_upwork_id_is_unique_per_user_not_globally(client: AsyncClient, auth_headers: dict, fake_embed):
    """Another tenant cannot squat on (or collide with) a user's Upwork proposal id."""
    other = await _second_user_headers(client)
    item = {"proposalId": "777", "jobTitle": "Azure", "coverLetter": "Letter", "status": "submitted"}

    r1 = await client.post(URL, headers=other, json={"proposals": [item]})
    assert r1.status_code == 200 and len(r1.json()) == 1
    r2 = await client.post(URL, headers=auth_headers, json={"proposals": [item]})
    assert r2.status_code == 200 and len(r2.json()) == 1

    # same user again -> upsert path, no duplicate row
    r3 = await client.post(URL, headers=auth_headers, json={"proposals": [{**item, "coverLetter": "Longer letter text"}]})
    assert r3.status_code == 200 and r3.json() == []
    async with TestSessionLocal() as s:
        rows = (await s.execute(select(Proposal).where(Proposal.upwork_proposal_id == "777"))).scalars().all()
    assert len(rows) == 2
    assert {r.user_id for r in rows} and len({r.user_id for r in rows}) == 2


def test_proposal_uniqueness_is_scoped_to_user():
    from sqlalchemy import UniqueConstraint

    table = Proposal.__table__
    assert not table.c.upwork_proposal_id.unique
    uniques = [tuple(c.name for c in con.columns) for con in table.constraints if isinstance(con, UniqueConstraint)]
    assert ("user_id", "upwork_proposal_id") in uniques


async def _seed_generated_letter(email: str, *, url: str, title: str, upwork_job_id=None):
    from app.models.cover_letter import CoverLetter
    from app.models.job import Job
    from app.models.user import User

    async with TestSessionLocal() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one()
        job = Job(user_id=user.id, upwork_url=url, title=title, description="desc", upwork_job_id=upwork_job_id)
        s.add(job)
        await s.flush()
        s.add(CoverLetter(user_id=user.id, job_id=job.id, content="Generated draft", model_used="m"))
        await s.commit()


@pytest.mark.asyncio
async def test_author_is_decided_by_server_from_generated_letters(client: AsyncClient, auth_headers: dict, fake_embed):
    other = await _second_user_headers(client)
    await _seed_generated_letter("test@example.com", url="https://www.upwork.com/jobs/~01aaa", title="Azure SQL migration")
    await _seed_generated_letter("test@example.com", url="https://www.upwork.com/jobs/x", title="Other",
                                 upwork_job_id="~01ccc")
    await _seed_generated_letter("other@example.com", url="https://www.upwork.com/jobs/~01bbb", title="Theirs")

    r = await client.post(URL, headers=auth_headers, json={"proposals": [
        # matched by job url
        {"proposalId": "a1", "jobTitle": "Renamed", "coverLetter": "x", "jobUrl": "https://www.upwork.com/jobs/~01aaa"},
        # matched by job title
        {"proposalId": "a2", "jobTitle": "azure sql migration ", "coverLetter": "x"},
        # matched by upwork job id in the url
        {"proposalId": "a3", "jobTitle": "Z", "coverLetter": "x", "jobUrl": "https://www.upwork.com/jobs/Title_~01ccc/"},
        # client claims an AI draft but none exists for this user
        {"proposalId": "a4", "jobTitle": "Unrelated", "coverLetter": "x", "author": "chris_edited_ai"},
        # another user's generated letter does not count; client-sent 'ai' is ignored too
        {"proposalId": "a5", "jobTitle": "Theirs", "coverLetter": "x", "jobUrl": "https://www.upwork.com/jobs/~01bbb", "author": "ai"},
    ]})
    assert r.status_code == 200
    by_id = {p["upwork_proposal_id"]: p["author"] for p in r.json()}
    assert by_id == {"a1": "chris_edited_ai", "a2": "chris_edited_ai", "a3": "chris_edited_ai", "a4": "chris", "a5": "chris"}


@pytest.mark.asyncio
async def test_scraped_letter_that_is_really_the_job_description_is_skipped(client: AsyncClient, auth_headers: dict, fake_embed):
    job = ("We need an experienced engineer to migrate our on-prem SQL Server estate to Azure "
           "with zero downtime and set up monitoring for the new environment.")
    r = await client.post(URL, headers=auth_headers, json={"proposals": [
        {"proposalId": "j1", "jobTitle": "A", "coverLetter": job, "jobDescription": job},
        {"proposalId": "j2", "jobTitle": "B", "coverLetter": "Job details:\n" + job.upper(), "jobDescription": job},
        {"proposalId": "j3", "jobTitle": "C", "coverLetter": job.replace("zero", "no").replace("new", "fresh"),
         "jobDescription": job},
        {"proposalId": "j4", "jobTitle": "D", "jobDescription": job,
         "coverLetter": "Moved a 160-server estate to Azure last year without an outage; happy to walk you through it."},
    ]})
    assert r.status_code == 200
    assert [p["upwork_proposal_id"] for p in r.json()] == ["j4"]
    async with TestSessionLocal() as s:
        ids = (await s.execute(select(Proposal.upwork_proposal_id))).scalars().all()
    assert sorted(ids) == ["j4"]
