"""Canonical proposal stages: proposals.stage (backfilled from status) + proposal_stage_events ledger.

The alias map is frozen here as it stood at this revision (app.services.proposal_status
STAGE_ALIASES); later additions to the app map do not rewrite history. Unmapped → 'unknown'.
The backfill writes no ledger rows: the ledger records changes seen from now on.

Revision ID: 027_proposal_stages
Revises: 026_fact_doubtful
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = '027_proposal_stages'
down_revision = '026_fact_doubtful'
branch_labels = None
depends_on = None

STAGE_ALIASES = {
    '7': 'submitted',
    'submitted': 'submitted',
    'viewed': 'viewed',
    'responded': 'replied',
    'replied': 'replied',
    'interview': 'interview',
    'interviewed': 'interview',
    'hired': 'hired',
    'declined': 'declined',
    'archived': 'closed',
    'closed': 'closed',
    'withdrawn': 'closed',
}


def backfill_sql() -> sa.TextClause:
    """One UPDATE: stage from lower(trim(status)) via the frozen map, else 'unknown'."""
    whens = " ".join(f"WHEN :raw{i} THEN :stage{i}" for i in range(len(STAGE_ALIASES)))
    params = {}
    for i, (raw, stage) in enumerate(STAGE_ALIASES.items()):
        params[f"raw{i}"], params[f"stage{i}"] = raw, stage
    return sa.text(
        f"UPDATE proposals SET stage = CASE lower(btrim(coalesce(status, ''))) {whens} ELSE 'unknown' END"
    ).bindparams(**params)


def upgrade() -> None:
    op.add_column(
        'proposals',
        sa.Column('stage', sa.String(20), nullable=False, server_default='unknown'),
    )
    op.get_bind().execute(backfill_sql())
    op.create_table(
        'proposal_stage_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('proposal_id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_stage', sa.String(20), nullable=True),
        sa.Column('to_stage', sa.String(20), nullable=False),
        sa.Column('raw_status', sa.String(50), nullable=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_proposal_stage_events_proposal_id', 'proposal_stage_events', ['proposal_id'])
    op.create_index('ix_proposal_stage_events_user_id', 'proposal_stage_events', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_proposal_stage_events_user_id', table_name='proposal_stage_events')
    op.drop_index('ix_proposal_stage_events_proposal_id', table_name='proposal_stage_events')
    op.drop_table('proposal_stage_events')
    op.drop_column('proposals', 'stage')
