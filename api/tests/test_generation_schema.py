"""Schema for generation v2: cover letter traceability + per-user flag (migration 023)."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.models.cover_letter import CoverLetter
from app.models.user import UserProfile

MIGRATION = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "023_generation_v2.py"


def test_cover_letter_traceability_columns():
    cols = CoverLetter.__table__.c
    assert isinstance(cols.brief.type, JSONB)
    assert isinstance(cols.fact_ids_used.type, ARRAY)
    assert isinstance(cols.voice_sample_ids.type, ARRAY)
    assert isinstance(cols.verify_warnings.type, JSONB)
    for name in ("brief", "fact_ids_used", "voice_sample_ids", "verify_warnings"):
        assert cols[name].nullable is True


def test_generation_v2_flag_is_not_null_default_false():
    col = UserProfile.__table__.c.generation_v2
    assert col.nullable is False
    assert col.server_default.arg.text == "false"


def test_migration_023_chains_onto_phase_1():
    spec = importlib.util.spec_from_file_location("m023", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "023_generation_v2"
    assert module.down_revision == "022_knowledge_layer"


@pytest.mark.asyncio
async def test_new_profiles_have_generation_v2_off(client, auth_headers_with_profile):
    from tests.conftest import test_engine

    async with test_engine.connect() as conn:
        value = (await conn.execute(text("SELECT generation_v2 FROM user_profiles"))).scalar_one()
    assert value is False
