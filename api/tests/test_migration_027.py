"""Migration 027: proposals.stage (backfilled from status) + proposal_stage_events ledger."""
import importlib.util
import pathlib
from unittest.mock import MagicMock

from sqlalchemy import select, text

from app.models.proposal import Proposal
from app.models.proposal_stage_event import ProposalStageEvent
from app.models.user import User
from app.services.proposal_status import STAGE_ALIASES
from tests.conftest import TestSessionLocal

MIGRATION = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "027_proposal_stages.py"


def _load():
    spec = importlib.util.spec_from_file_location("mig_027_proposal_stages", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_chain():
    mod = _load()
    assert mod.revision == "027_proposal_stages"
    assert mod.down_revision == "026_fact_doubtful"


def test_frozen_map_agrees_with_app_map():
    """The app map may grow; it must never re-map a value the migration backfilled."""
    frozen = _load().STAGE_ALIASES
    assert {k: STAGE_ALIASES.get(k) for k in frozen} == frozen


def test_upgrade_and_downgrade_shape(monkeypatch):
    mod = _load()
    fake_op = MagicMock()
    monkeypatch.setattr(mod, "op", fake_op)
    mod.upgrade()
    [add] = fake_op.add_column.call_args_list
    assert (add.args[0], add.args[1].name, add.args[1].nullable) == ("proposals", "stage", False)
    assert fake_op.create_table.call_args.args[0] == "proposal_stage_events"
    assert fake_op.get_bind.return_value.execute.call_count == 1
    mod.downgrade()
    assert fake_op.drop_table.call_args.args == ("proposal_stage_events",)
    assert fake_op.drop_column.call_args.args == ("proposals", "stage")


def test_models_match_migration():
    assert not Proposal.__table__.c["stage"].nullable
    cols = set(ProposalStageEvent.__table__.c.keys())
    assert cols == {"id", "proposal_id", "user_id", "from_stage", "to_stage", "raw_status", "source", "created_at"}


async def test_backfill_maps_status_and_writes_no_ledger_rows(db_session):
    mod = _load()
    user = User(email="backfill-027@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    raws = {"a": "8", "b": "7", "c": "Responded", "d": " archived ", "e": None, "f": "interviewed"}
    ids = {}
    for key, raw in raws.items():
        p = Proposal(user_id=user.id, cover_letter_text="x", status=raw)
        db_session.add(p)
        await db_session.flush()
        ids[key] = p.id
    await db_session.commit()
    async with TestSessionLocal() as s:  # simulate pre-027 rows: no stage, no ledger
        await s.execute(text("UPDATE proposals SET stage = 'hired'"))
        await s.execute(text("DELETE FROM proposal_stage_events"))
        await s.execute(mod.backfill_sql())
        await s.commit()
        stages = {p.id: p.stage for p in (await s.execute(select(Proposal))).scalars()}
        events = (await s.execute(select(ProposalStageEvent))).scalars().all()
    assert {k: stages[v] for k, v in ids.items()} == {
        "a": "unknown", "b": "submitted", "c": "replied", "d": "closed", "e": "unknown", "f": "interview",
    }
    assert events == []
