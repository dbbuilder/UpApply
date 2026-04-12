"""Add job_queue and user_autonomy_profiles tables for autonomous agent.

Revision ID: 016_job_queue_and_autonomy
Revises: 015_client_locations
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '016_job_queue_and_autonomy'
down_revision = '015_client_locations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- user_autonomy_profiles -------------------------------------------
    op.create_table(
        'user_autonomy_profiles',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('level', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('level_since', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('suggestions_shown', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('suggestions_approved', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proposals_submitted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proposals_responded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proposals_hired', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_edit_distance', sa.Float(), nullable=True),
        sa.Column('last_evaluated', sa.DateTime(timezone=True), nullable=True),
        sa.Column('locked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('score_threshold', sa.Float(), nullable=False, server_default='55.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # --- job_queue --------------------------------------------------------
    op.create_table(
        'job_queue',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('upwork_url', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('skills', JSONB(), nullable=True, server_default='[]'),
        sa.Column('budget_amount', sa.Text(), nullable=True),
        sa.Column('budget_type', sa.Text(), nullable=True),
        sa.Column('client_info', JSONB(), nullable=True),
        sa.Column('ai_score', sa.Float(), nullable=True),
        sa.Column('ai_reasoning', sa.Text(), nullable=True),
        sa.Column('chips', JSONB(), nullable=True, server_default='[]'),
        sa.Column('status', sa.String(20), nullable=False, server_default='suggested'),
        sa.Column('source', sa.String(20), nullable=False, server_default='agent'),
        sa.Column('source_query_id', sa.String(36),
                  sa.ForeignKey('search_queries.id', ondelete='SET NULL'), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True),
                  server_default=sa.text("now() + interval '7 days'")),
        sa.UniqueConstraint('user_id', 'upwork_url', name='uq_job_queue_user_url'),
    )

    op.create_index('ix_job_queue_user_id', 'job_queue', ['user_id'])
    op.create_index('ix_job_queue_status', 'job_queue', ['status'])
    op.create_index('ix_job_queue_user_status', 'job_queue', ['user_id', 'status'])


def downgrade() -> None:
    op.drop_table('job_queue')
    op.drop_table('user_autonomy_profiles')
