"""Add user_profiles.freelancer_location: where the freelancer is (country or region).

Used by the client must-have check (app/services/job_requirements.py, Chris 2026-11-11) so a
"U.S. only" job is judged against the freelancer's own location. Nullable: not set = unknown,
never penalised.

Revision ID: 030_freelancer_location
Revises: 029_job_queue_score_breakdown
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = '030_freelancer_location'
down_revision = '029_job_queue_score_breakdown'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user_profiles', sa.Column('freelancer_location', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('user_profiles', 'freelancer_location')
