"""Add submission tracking fields to cover_letters.

Captures what was actually submitted (may differ from generated) and
whether the letter was marked as submitted from the extension.

Revision ID: 013_cl_submission_tracking
Revises: 012_add_proposal_anchors
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa


revision = '013_cl_submission_tracking'
down_revision = '012_add_proposal_anchors'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # submitted_text: what was actually sent (user may have edited the generated letter)
    op.add_column('cover_letters', sa.Column('submitted_text', sa.Text, nullable=True))
    # was_submitted: True once the user clicks "Mark as Submitted" in the extension
    op.add_column('cover_letters', sa.Column('was_submitted', sa.Boolean, server_default='false', nullable=False))
    # submitted_at: timestamp of submission
    op.add_column('cover_letters', sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('cover_letters', 'submitted_at')
    op.drop_column('cover_letters', 'was_submitted')
    op.drop_column('cover_letters', 'submitted_text')
