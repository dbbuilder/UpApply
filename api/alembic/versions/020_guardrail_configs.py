"""Add user_guardrail_configs table for per-user autonomous agent guardrails.

Revision ID: 020_guardrail_configs
Revises: 019_job_queue_submission
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = '020_guardrail_configs'
down_revision = '019_job_queue_submission'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_guardrail_configs',
        sa.Column('user_id', sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        # Hard limits for Level 5 autonomous operation
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('max_proposals_per_day', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('min_connects_reserve', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('max_bid_hourly', sa.Numeric(10, 2), nullable=True),   # NULL = no cap
        sa.Column('max_bid_fixed', sa.Numeric(10, 2), nullable=True),    # NULL = no cap
        sa.Column('min_score_threshold', sa.Float(), nullable=False, server_default='60.0'),
        # Pause window — agent won't run between pause_start_hour and pause_end_hour (UTC)
        sa.Column('pause_start_hour', sa.Integer(), nullable=True),
        sa.Column('pause_end_hour', sa.Integer(), nullable=True),
        # Connects tracking (agent updates this as it tracks spending)
        sa.Column('connects_balance', sa.Integer(), nullable=True),
        sa.Column('connects_balance_updated_at', sa.DateTime(timezone=True), nullable=True),
        # Digest notification preference
        sa.Column('digest_email', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('user_guardrail_configs')
