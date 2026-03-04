"""Add search_queries table and search_query_id FK on jobs.

Revision ID: 009_add_search_queries
Revises: 008_add_job_source_fields
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa


revision = '009_add_search_queries'
down_revision = '008_add_job_source_fields'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'search_queries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('url_params', sa.Text(), nullable=True),
        sa.Column('source', sa.String(20), nullable=False, server_default='manual'),
        sa.Column('parent_query_id', sa.String(36), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('run_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_jobs_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_match_score', sa.Float(), nullable=True),
        sa.Column('high_score_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index('ix_search_queries_user_id', 'search_queries', ['user_id'])
    op.create_index(
        'uq_search_queries_user_query',
        'search_queries',
        [sa.text('user_id'), sa.text('lower(trim(query))')],
        unique=True,
    )
    op.add_column(
        'jobs',
        sa.Column('search_query_id', sa.String(36),
                  sa.ForeignKey('search_queries.id', ondelete='SET NULL'),
                  nullable=True),
    )


def downgrade():
    op.drop_column('jobs', 'search_query_id')
    op.drop_index('uq_search_queries_user_query', table_name='search_queries')
    op.drop_index('ix_search_queries_user_id', table_name='search_queries')
    op.drop_table('search_queries')
