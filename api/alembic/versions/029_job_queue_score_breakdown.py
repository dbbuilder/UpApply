"""Job-fit rubric: job_queue.score_breakdown holds the per-dimension score beside ai_score.

Shadow week first (docs/superpowers/plans/2026-11-04-job-fit-rubric.md, migration approved by
Chris 2026-11-05): the ingest writes {total, dimensions, red_flags, model, rubric_version} here and
leaves ai_score, the threshold and the status as they were. Nullable: older rows and failed
rubric calls stay NULL.

Revision ID: 029_job_queue_score_breakdown
Revises: 028_learned_rules
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '029_job_queue_score_breakdown'
down_revision = '028_learned_rules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('job_queue', sa.Column('score_breakdown', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('job_queue', 'score_breakdown')
