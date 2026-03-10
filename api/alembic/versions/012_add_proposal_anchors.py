"""Add proposal_anchors to user_profiles for per-user cover letter credential routing.

Revision ID: 012_add_proposal_anchors
Revises: 011_add_work_logs
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '012_add_proposal_anchors'
down_revision = '011_add_work_logs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # proposal_anchors is a JSONB dict with keys:
    #   "always_include": list[str]  — items to weave into every letter when profile data supports it
    #   "cto": str                   — credential guidance for CTO/leadership jobs
    #   "saas": str                  — guidance for SaaS/MVP jobs
    #   "sql": str                   — guidance for SQL/data jobs
    #   "cloud": str                 — guidance for cloud/Azure/AWS jobs
    #   "ai": str                    — guidance for AI/ML/RAG jobs
    #   "fullstack": str             — guidance for full-stack jobs
    op.add_column('user_profiles', sa.Column('proposal_anchors', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('user_profiles', 'proposal_anchors')
