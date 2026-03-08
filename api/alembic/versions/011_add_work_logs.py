"""Add work_logs table for time/task capture

Revision ID: 011_add_work_logs
Revises: 010_add_job_reviews
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa

revision = '011_add_work_logs'
down_revision = '010_add_job_reviews'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'work_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('contract_title', sa.String(500), nullable=False),
        sa.Column('upwork_contract_id', sa.String(100), nullable=True),
        sa.Column('task_description', sa.Text(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('attachment_filename', sa.String(500), nullable=True),
        sa.Column('attachment_text', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_work_logs_user_id_created', 'work_logs', ['user_id', 'created_at'])


def downgrade():
    op.drop_index('ix_work_logs_user_id_created', table_name='work_logs')
    op.drop_table('work_logs')
