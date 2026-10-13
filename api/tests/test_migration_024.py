"""Migration 024 (refine + learn loop) and CoverLetter ORM columns."""
import importlib.util
import pathlib
from unittest.mock import MagicMock

from app.models.cover_letter import CoverLetter

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "024_refine_loop.py"
)
EXPECTED = ["refine_messages", "final_text", "final_answers", "edit_distance_pct"]
EXPECTED_ADDS = [("cover_letters", n) for n in EXPECTED] + [("proposals", "facts_credited_at")]


def _load():
    spec = importlib.util.spec_from_file_location("mig_024_refine_loop", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_chain():
    mod = _load()
    assert mod.revision == "024_refine_loop"
    assert mod.down_revision == "023_generation_v2"


def test_upgrade_adds_columns(monkeypatch):
    mod = _load()
    fake_op = MagicMock()
    monkeypatch.setattr(mod, "op", fake_op)
    mod.upgrade()
    added = [(c.args[0], c.args[1].name) for c in fake_op.add_column.call_args_list]
    assert added == EXPECTED_ADDS
    assert all(c.args[1].nullable for c in fake_op.add_column.call_args_list)


def test_downgrade_drops_columns_in_reverse(monkeypatch):
    mod = _load()
    fake_op = MagicMock()
    monkeypatch.setattr(mod, "op", fake_op)
    mod.downgrade()
    dropped = [c.args for c in fake_op.drop_column.call_args_list]
    assert dropped == list(reversed(EXPECTED_ADDS))


def test_cover_letter_model_has_columns():
    cols = CoverLetter.__table__.c
    for name in EXPECTED:
        assert name in cols
        assert cols[name].nullable


def test_proposal_model_has_credit_marker():
    from app.models.proposal import Proposal

    col = Proposal.__table__.c["facts_credited_at"]
    assert col.nullable
