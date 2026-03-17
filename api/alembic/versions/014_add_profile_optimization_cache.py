"""Add profile optimization cache columns to user_profiles.

Stores the cached AI optimization result and its timestamp so the
expensive analysis call can be avoided on repeat visits.

Revision ID: 014_add_profile_optimization_cache
Revises: 013_cl_submission_tracking
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '014_add_profile_optimization_cache'
down_revision = '013_cl_submission_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user_profiles', sa.Column('optimization_result', JSONB, nullable=True))
    op.add_column('user_profiles', sa.Column('optimization_cached_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('user_profiles', 'optimization_cached_at')
    op.drop_column('user_profiles', 'optimization_result')
