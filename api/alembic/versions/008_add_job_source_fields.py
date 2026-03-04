"""Add source, is_saved, and expires_at to jobs table.

Revision ID: 008_add_job_source_fields
Revises: 007_lowercase_emails
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa

revision = '008_add_job_source_fields'
down_revision = '007_lowercase_emails'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('is_saved', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('jobs', sa.Column('source', sa.String(20), nullable=True))
    op.add_column('jobs', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('jobs', 'expires_at')
    op.drop_column('jobs', 'source')
    op.drop_column('jobs', 'is_saved')
