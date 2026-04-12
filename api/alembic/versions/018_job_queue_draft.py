"""Add draft_cover_letter and draft_status columns to job_queue.

Revision ID: 018_job_queue_draft
Revises: 017_outcome_events
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = '018_job_queue_draft'
down_revision = '017_outcome_events'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('job_queue', sa.Column('draft_cover_letter', sa.Text(), nullable=True))
    # none | generating | ready | sent
    op.add_column('job_queue', sa.Column('draft_status', sa.String(20), nullable=True,
                                         server_default='none'))
    op.add_column('job_queue', sa.Column('draft_generated_at', sa.DateTime(timezone=True),
                                          nullable=True))
    op.add_column('job_queue', sa.Column('proposals_submitted', sa.Integer(), nullable=True,
                                          server_default='0'))


def downgrade() -> None:
    op.drop_column('job_queue', 'proposals_submitted')
    op.drop_column('job_queue', 'draft_generated_at')
    op.drop_column('job_queue', 'draft_status')
    op.drop_column('job_queue', 'draft_cover_letter')
