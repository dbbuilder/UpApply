"""Add outcome_events table for agent feedback loop.

Revision ID: 017_outcome_events
Revises: 016_job_queue_and_autonomy
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = '017_outcome_events'
down_revision = '016_job_queue_and_autonomy'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'outcome_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('job_queue_id', sa.String(36),
                  sa.ForeignKey('job_queue.id', ondelete='SET NULL'),
                  nullable=True),
        # Event type: suggested | approved | rejected | submitted | responded | hired
        sa.Column('event_type', sa.String(20), nullable=False),
        # Optional metadata: rejection_reason, edit_distance_pct, etc.
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    op.create_index('ix_outcome_events_user_id', 'outcome_events', ['user_id'])
    op.create_index('ix_outcome_events_user_event', 'outcome_events', ['user_id', 'event_type'])
    op.create_index('ix_outcome_events_created_at', 'outcome_events', ['created_at'])


def downgrade() -> None:
    op.drop_table('outcome_events')
