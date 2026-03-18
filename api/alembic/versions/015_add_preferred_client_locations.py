"""Add preferred_client_locations to user_profiles.

Stores a list of preferred client location tiers so the geo modifier
in job_analysis.py can respect user preferences rather than using
hardcoded defaults.

Revision ID: 015_add_preferred_client_locations
Revises: 014_profile_opt_cache
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '015_client_locations'
down_revision = '014_profile_opt_cache'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user_profiles', sa.Column('preferred_client_locations', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('user_profiles', 'preferred_client_locations')
