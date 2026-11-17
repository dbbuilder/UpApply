"""Add job_reviews.details: what the job card showed when it was scored.

Posted time, client country, spend and rating, payment verified, proposals and experience level,
for the Find tab's display and its date / pay / country filters (Chris 2026-11-15). Nullable:
jobs scored before this have none.

Revision ID: 031_job_review_details
Revises: 030_freelancer_location
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = '031_job_review_details'
down_revision = '030_freelancer_location'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('job_reviews', sa.Column('details', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('job_reviews', 'details')
