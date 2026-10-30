"""Learned rules: writing rules proposed from the user's own edits, accepted or rejected by the user.

A rule is stored as 'proposed' and only the user moves it to 'accepted' or 'rejected', once
(decided_at records when). Nothing is ever auto-accepted.

Revision ID: 028_learned_rules
Revises: 027_proposal_stages
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = '028_learned_rules'
down_revision = '027_proposal_stages'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'learned_rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('rule', sa.Text(), nullable=False),
        sa.Column('evidence_quote', sa.Text(), nullable=False),
        sa.Column('times_seen', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(20), nullable=False, server_default='proposed'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('proposed', 'accepted', 'rejected')", name='ck_learned_rules_status'
        ),
    )
    op.create_index('ix_learned_rules_user_id', 'learned_rules', ['user_id'])
    # One copy of a rule per user (case-insensitive): concurrent proposals cannot duplicate it.
    op.create_index(
        'uq_learned_rules_user_rule', 'learned_rules', ['user_id', sa.text('lower(rule)')], unique=True
    )


def downgrade() -> None:
    op.drop_index('uq_learned_rules_user_rule', table_name='learned_rules')
    op.drop_index('ix_learned_rules_user_id', table_name='learned_rules')
    op.drop_table('learned_rules')
