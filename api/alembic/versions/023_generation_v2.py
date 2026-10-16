"""Generation v2: cover letter traceability columns + per-user generation_v2 flag.

Revision ID: 023_generation_v2
Revises: 022_knowledge_layer
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB


revision = '023_generation_v2'
down_revision = '022_knowledge_layer'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('cover_letters', sa.Column('brief', JSONB, nullable=True))
    op.add_column('cover_letters', sa.Column('fact_ids_used', ARRAY(sa.String(36)), nullable=True))
    op.add_column('cover_letters', sa.Column('voice_sample_ids', ARRAY(sa.String(36)), nullable=True))
    op.add_column('cover_letters', sa.Column('verify_warnings', JSONB, nullable=True))
    op.add_column(
        'user_profiles',
        sa.Column('generation_v2', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('user_profiles', 'generation_v2')
    op.drop_column('cover_letters', 'verify_warnings')
    op.drop_column('cover_letters', 'voice_sample_ids')
    op.drop_column('cover_letters', 'fact_ids_used')
    op.drop_column('cover_letters', 'brief')
