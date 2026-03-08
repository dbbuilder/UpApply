"""Add job_reviews table for scored job ratings and self-improvement.

Revision ID: 010_add_job_reviews
Revises: 009_add_search_queries
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa

revision = '010_add_job_reviews'
down_revision = '009_add_search_queries'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'job_reviews',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('upwork_job_url', sa.String(500), nullable=False),
        sa.Column('upwork_job_id', sa.String(100), nullable=True),
        sa.Column('job_title', sa.String(500), nullable=False),
        sa.Column('ai_score', sa.Float(), nullable=True),
        sa.Column('chips', sa.JSON(), nullable=True),
        sa.Column('budget_amount', sa.String(100), nullable=True),
        sa.Column('budget_type', sa.String(20), nullable=True),
        sa.Column('user_rating', sa.Integer(), nullable=True),
        sa.Column('user_comment', sa.Text(), nullable=True),
        sa.Column('scored_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('user_id', 'upwork_job_url', name='uq_job_review_user_url'),
    )


def downgrade() -> None:
    op.drop_table('job_reviews')
