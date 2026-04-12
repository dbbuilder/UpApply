"""Add global_signal_pool table for cross-user anonymized learning.

Revision ID: 021_global_signal_pool
Revises: 020_guardrail_configs
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = '021_global_signal_pool'
down_revision = '020_guardrail_configs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'global_signal_pool',
        sa.Column('id', sa.String(36), primary_key=True),
        # Anonymized: SHA-256 of sorted skill names (no user_id, no text)
        sa.Column('skill_hash', sa.String(64), nullable=False),
        # Outcome code: queued|approved|rejected|drafted|submitted|viewed|responded|hired|declined
        sa.Column('outcome_code', sa.String(20), nullable=False),
        # Score the agent gave this job at submission time
        sa.Column('score_at_submission', sa.Float(), nullable=True),
        # Edit distance: how much user changed the draft (0.0 = none, 1.0 = rewrote entirely)
        sa.Column('edit_distance_pct', sa.Float(), nullable=True),
        # Aggregate counts (contributions from this signal)
        sa.Column('weight', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    op.create_index('ix_signal_pool_skill_hash', 'global_signal_pool', ['skill_hash'])
    op.create_index('ix_signal_pool_outcome', 'global_signal_pool', ['outcome_code'])
    op.create_index('ix_signal_pool_skill_outcome', 'global_signal_pool',
                    ['skill_hash', 'outcome_code'])


def downgrade() -> None:
    op.drop_table('global_signal_pool')
