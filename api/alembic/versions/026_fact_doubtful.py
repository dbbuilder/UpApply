"""Add facts.doubtful: a review hint that marks a candidate doubtful without rejecting it.

It never changes status, generation or auto-approval.

Revision ID: 026_fact_doubtful
Revises: 025_relabel_bio_memories
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision = '026_fact_doubtful'
down_revision = '025_relabel_bio_memories'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'facts',
        sa.Column('doubtful', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('facts', 'doubtful')
