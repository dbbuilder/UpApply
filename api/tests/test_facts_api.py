"""Integration tests for /api/v1/facts review endpoints (embeddings mocked)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.fact import Fact
from tests.conftest import TestSessionLocal
from tests.vector_utils import make_fake_embedder, unit

BASE = "/api/v1/facts"


@pytest.fixture
def fake_embed():
    mock = make_fake_embedder()
    with patch("app.services.facts.generate_embedding", mock), \
         patch("app.api.v1.facts.generate_embedding", mock):
        yield mock


async def _user_id(client: AsyncClient, headers: dict) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


async def _seed_fact(user_id: str, statement: str, axis: int, **kw) -> str:
    async with TestSessionLocal() as s:
        fact = Fact(
            user_id=user_id, kind=kw.pop("kind", "metric"), statement=statement,
            status=kw.pop("status", "candidate"), strength=kw.pop("strength", 0.6),
            source_type="chatgpt_user_turn", source_ref="conv-1",
            sources=[{"source_type": "chatgpt_user_turn", "source_ref": "conv-1", "snippet": "quote"}],
            embedding=unit(1000 + axis), **kw,
        )
        s.add(fact)
        await s.commit()
        return fact.id


@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient):
    r = await client.get(BASE)
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_manual_fact_is_approved(client: AsyncClient, auth_headers: dict, fake_embed):
    r = await client.post(BASE, headers=auth_headers, json={
        "kind": "credential", "statement": "Holds an MBA.", "job_types": ["cto"],
    })
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "approved"
    assert body["source_type"] == "manual"
    assert body["job_types"] == ["cto"]
    fake_embed.assert_awaited_once_with("Holds an MBA.")


@pytest.mark.asyncio
async def test_list_filters_by_status_and_kind(client: AsyncClient, auth_headers: dict):
    uid = await _user_id(client, auth_headers)
    await _seed_fact(uid, "Candidate metric", 1)
    await _seed_fact(uid, "Approved metric", 2, status="approved")
    await _seed_fact(uid, "Candidate project", 3, kind="project")

    r = await client.get(BASE, headers=auth_headers, params={"status": "candidate"})
    assert sorted(f["statement"] for f in r.json()) == ["Candidate metric", "Candidate project"]

    r = await client.get(BASE, headers=auth_headers, params={"status": "candidate", "kind": "project"})
    assert [f["statement"] for f in r.json()] == ["Candidate project"]
    assert r.json()[0]["sources"][0]["snippet"] == "quote"


@pytest.mark.asyncio
async def test_patch_edits_reembeds_and_rejects(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _user_id(client, auth_headers)
    fid = await _seed_fact(uid, "Old wording", 4)

    r = await client.patch(f"{BASE}/{fid}", headers=auth_headers, json={"statement": "New wording"})
    assert r.status_code == 200
    assert r.json()["statement"] == "New wording"
    fake_embed.assert_awaited_once_with("New wording")

    r = await client.patch(f"{BASE}/{fid}", headers=auth_headers, json={"status": "rejected"})
    assert r.json()["status"] == "rejected"
    assert fake_embed.await_count == 1  # status-only change does not re-embed

    r = await client.get(BASE, headers=auth_headers, params={"status": "rejected"})
    assert [f["id"] for f in r.json()] == [fid]


@pytest.mark.asyncio
async def test_patch_other_users_fact_404(client: AsyncClient, auth_headers: dict):
    uid = await _user_id(client, auth_headers)
    fid = await _seed_fact(uid, "Mine", 5)
    other = await client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "testpass123"})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    r = await client.patch(f"{BASE}/{fid}", headers=other_headers, json={"status": "approved"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_bulk_approve(client: AsyncClient, auth_headers: dict):
    uid = await _user_id(client, auth_headers)
    a = await _seed_fact(uid, "A", 6)
    b = await _seed_fact(uid, "B", 7)
    await _seed_fact(uid, "C", 8)

    r = await client.post(f"{BASE}/bulk-approve", headers=auth_headers, json={"ids": [a, b]})
    assert r.status_code == 200
    assert r.json() == {"approved": 2}

    r = await client.get(BASE, headers=auth_headers, params={"status": "candidate"})
    assert [f["statement"] for f in r.json()] == ["C"]


@pytest.mark.asyncio
async def test_patch_null_on_required_field_is_ignored(client: AsyncClient, auth_headers: dict, fake_embed):
    uid = await _user_id(client, auth_headers)
    fid = await _seed_fact(uid, "Keep me", 9, detail="Some detail")

    r = await client.patch(f"{BASE}/{fid}", headers=auth_headers, json={"statement": None, "status": None, "detail": None})
    assert r.status_code == 200
    assert r.json()["statement"] == "Keep me"
    assert r.json()["status"] == "candidate"
    assert r.json()["detail"] is None  # detail is nullable, so null clears it


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_status,existing_strength", [
    ("rejected", 0.9),   # a rejected fact must not be resurrected with its old wording
    ("candidate", 0.95),  # an untrusted, high-strength candidate must not win over typed text
])
async def test_manual_create_near_duplicate_keeps_user_wording(
    client: AsyncClient, auth_headers: dict, existing_status: str, existing_strength: float
):
    uid = await _user_id(client, auth_headers)
    fid = await _seed_fact(
        uid, "Migrated 120 servers", 20, status=existing_status, strength=existing_strength
    )
    same_vector = AsyncMock(return_value=unit(1000 + 20))  # identical embedding -> merge path
    with patch("app.services.facts.generate_embedding", same_vector), \
         patch("app.api.v1.facts.generate_embedding", same_vector):
        r = await client.post(BASE, headers=auth_headers, json={
            "kind": "metric", "statement": "Migrated 160 servers", "detail": "Azure, 2023",
        })
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == fid
    assert body["statement"] == "Migrated 160 servers"
    assert body["detail"] == "Azure, 2023"
    assert body["status"] == "approved"
    assert body["sources"][-1]["source_type"] == "manual"
    assert body["sources"][-1]["snippet"] == "Migrated 160 servers"
