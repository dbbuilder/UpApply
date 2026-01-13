"""Add beta_feedback table for tester feedback collection.

Revision ID: 006
Revises: 005
Create Date: 2025-01-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'beta_feedback',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('feedback_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('page_url', sa.Text(), nullable=True),
        sa.Column('extension_version', sa.String(20), nullable=True),
        sa.Column('browser_info', sa.String(255), nullable=True),
        sa.Column('user_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # Index for querying by type
    op.create_index('ix_beta_feedback_type', 'beta_feedback', ['feedback_type'])
    op.create_index('ix_beta_feedback_created_at', 'beta_feedback', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_beta_feedback_created_at', 'beta_feedback')
    op.drop_index('ix_beta_feedback_type', 'beta_feedback')
    op.drop_table('beta_feedback')
