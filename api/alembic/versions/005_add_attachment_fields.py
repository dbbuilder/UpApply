"""Add attachment text fields to jobs table.

Revision ID: 005_add_attachment_fields
Revises: 004_add_screening_answers_and_proposals
Create Date: 2025-01-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005_add_attachment_fields'
down_revision: Union[str, None] = '004_screening_proposals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to jobs table for attachment text extraction
    op.add_column('jobs', sa.Column('full_description', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('attachment_text', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('attachment_metadata', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('jobs', 'attachment_metadata')
    op.drop_column('jobs', 'attachment_text')
    op.drop_column('jobs', 'full_description')
