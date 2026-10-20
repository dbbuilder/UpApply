"""Migration 026 (facts.doubtful review hint) and Fact ORM column."""
import importlib.util
import pathlib
from unittest.mock import MagicMock

from app.models.fact import Fact

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "026_fact_doubtful.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mig_026_fact_doubtful", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_chain():
    mod = _load()
    assert mod.revision == "026_fact_doubtful"
    assert mod.down_revision == "025_relabel_bio_memories"


def test_upgrade_adds_not_null_column_defaulting_false(monkeypatch):
    mod = _load()
    fake_op = MagicMock()
    monkeypatch.setattr(mod, "op", fake_op)
    mod.upgrade()
    [call] = fake_op.add_column.call_args_list
    table, col = call.args
    assert (table, col.name) == ("facts", "doubtful")
    assert not col.nullable
    assert str(col.server_default.arg) == "false"


def test_downgrade_drops_column(monkeypatch):
    mod = _load()
    fake_op = MagicMock()
    monkeypatch.setattr(mod, "op", fake_op)
    mod.downgrade()
    assert [c.args for c in fake_op.drop_column.call_args_list] == [("facts", "doubtful")]


def test_fact_model_has_column():
    col = Fact.__table__.c["doubtful"]
    assert not col.nullable
