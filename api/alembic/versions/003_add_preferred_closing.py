"""Add preferred_closing to user_profiles.

Revision ID: 003_add_preferred_closing
Revises: 002_add_cover_letter_columns
Create Date: 2026-01-12
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '003_add_preferred_closing'
down_revision = '002_add_cover_letter_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user_profiles', sa.Column('preferred_closing', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_profiles', 'preferred_closing')
