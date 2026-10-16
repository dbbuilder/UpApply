"""Migration 025: relabel Chris's curated bio memories so /facts/from-memories trusts them."""
import importlib.util
import pathlib
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.models.memory import Memory
from app.models.user import User
from tests.conftest import TestSessionLocal

MIGRATION = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "025_relabel_bio_memories.py"


def _load():
    spec = importlib.util.spec_from_file_location("mig_025_relabel", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _captured(mod, monkeypatch, step):
    fake_op = MagicMock()
    monkeypatch.setattr(mod, "op", fake_op)
    step()
    [call] = fake_op.get_bind.return_value.execute.call_args_list
    return call.args


def test_revision_chain():
    mod = _load()
    assert mod.revision == "025_relabel_bio_memories"
    assert mod.down_revision == "024_refine_loop"
    assert len(mod.TITLES) == 14


async def _seed():
    async with TestSessionLocal() as s:
        chris = User(email="chris@servicevision.net", hashed_password="x")
        other = User(email="someone@example.com", hashed_password="x")
        s.add_all([chris, other])
        await s.flush()
        bio = "Migrated 160-server datacenter to Azure hybrid cloud"
        rows = {
            "bio": Memory(user_id=chris.id, title=bio, content="c", source="chatgpt_corpus"),
            "corpus": Memory(user_id=chris.id, title="Some past proposal", content="c", source="chatgpt_corpus"),
            "other_user": Memory(user_id=other.id, title=bio, content="c", source="chatgpt_corpus"),
        }
        s.add_all(rows.values())
        await s.commit()
        return {k: v.id for k, v in rows.items()}


async def _sources(ids):
    async with TestSessionLocal() as s:
        found = {m.id: m.source for m in (await s.execute(select(Memory))).scalars()}
    return {k: found[v] for k, v in ids.items()}


@pytest.mark.asyncio
async def test_upgrade_relabels_only_chris_curated_titles_and_downgrade_reverts(client, monkeypatch):
    mod = _load()
    ids = await _seed()

    async with TestSessionLocal() as s:
        await s.execute(*_captured(mod, monkeypatch, mod.upgrade))
        await s.commit()
    assert await _sources(ids) == {"bio": "bio_import", "corpus": "chatgpt_corpus", "other_user": "chatgpt_corpus"}

    async with TestSessionLocal() as s:
        await s.execute(*_captured(mod, monkeypatch, mod.downgrade))
        await s.commit()
    assert await _sources(ids) == {"bio": "chatgpt_corpus", "corpus": "chatgpt_corpus", "other_user": "chatgpt_corpus"}
