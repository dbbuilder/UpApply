"""Add missing cover_letters columns.

Revision ID: 002_add_cover_letter_columns
Revises: 001_initial_schema
Create Date: 2026-01-12
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '002_add_cover_letter_columns'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add missing columns to cover_letters table
    op.add_column('cover_letters', sa.Column('prompt_version', sa.String(50), nullable=True))
    op.add_column('cover_letters', sa.Column('ai_confidence', sa.Numeric(3, 2), nullable=True))
    op.add_column('cover_letters', sa.Column('token_count', sa.Integer(), nullable=True))
    op.add_column('cover_letters', sa.Column('word_count', sa.Integer(), nullable=True))
    op.add_column('cover_letters', sa.Column('is_final', sa.Boolean(), server_default='false'))


def downgrade() -> None:
    op.drop_column('cover_letters', 'is_final')
    op.drop_column('cover_letters', 'word_count')
    op.drop_column('cover_letters', 'token_count')
    op.drop_column('cover_letters', 'ai_confidence')
    op.drop_column('cover_letters', 'prompt_version')
