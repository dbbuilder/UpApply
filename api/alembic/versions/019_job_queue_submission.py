"""Add submission tracking columns to job_queue.

Revision ID: 019_job_queue_submission
Revises: 018_job_queue_draft
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = '019_job_queue_submission'
down_revision = '018_job_queue_draft'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Submission metadata recorded when user confirms auto-fill
    op.add_column('job_queue', sa.Column('bid_amount', sa.Numeric(10, 2), nullable=True))
    op.add_column('job_queue', sa.Column('connects_spent', sa.Integer(), nullable=True))
    op.add_column('job_queue', sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True))

    # Response/view tracking (recorded by background script)
    op.add_column('job_queue', sa.Column('last_status_check', sa.DateTime(timezone=True), nullable=True))
    op.add_column('job_queue', sa.Column('upwork_proposal_id', sa.String(64), nullable=True))
    op.add_column('job_queue', sa.Column('client_response_type',
                                          sa.String(20), nullable=True))
    # none | viewed | responded | invited | declined
    op.add_column('job_queue', sa.Column('client_response_at', sa.DateTime(timezone=True), nullable=True))

    op.create_index(
        'ix_job_queue_upwork_proposal_id', 'job_queue', ['upwork_proposal_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_job_queue_upwork_proposal_id', table_name='job_queue')
    op.drop_column('job_queue', 'client_response_at')
    op.drop_column('job_queue', 'client_response_type')
    op.drop_column('job_queue', 'upwork_proposal_id')
    op.drop_column('job_queue', 'last_status_check')
    op.drop_column('job_queue', 'connects_spent')
    op.drop_column('job_queue', 'bid_amount')
    op.drop_column('job_queue', 'confirmed_at')
