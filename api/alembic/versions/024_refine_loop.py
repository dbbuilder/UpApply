"""Add refine-thread and submitted-final columns to cover_letters.

Revision ID: 024_refine_loop
Revises: 023_generation_v2
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '024_refine_loop'
down_revision = '023_generation_v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Refine thread: [{role, content, screening_answers?, warnings?, at}]
    op.add_column('cover_letters', sa.Column('refine_messages', postgresql.JSONB(), nullable=True))
    # What Chris actually submitted on Upwork (captured on Submit click)
    op.add_column('cover_letters', sa.Column('final_text', sa.Text(), nullable=True))
    op.add_column('cover_letters', sa.Column('final_answers', postgresql.JSONB(), nullable=True))
    # Word-level edit distance draft → final (0.0 identical, 1.0 rewritten)
    op.add_column('cover_letters', sa.Column('edit_distance_pct', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('cover_letters', 'edit_distance_pct')
    op.drop_column('cover_letters', 'final_answers')
    op.drop_column('cover_letters', 'final_text')
    op.drop_column('cover_letters', 'refine_messages')
