"""Add screening_answers and proposals tables.

Revision ID: 004_add_screening_answers_and_proposals
Revises: 003_add_preferred_closing
Create Date: 2026-01-12
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers
revision = '004_add_screening_answers_and_proposals'
down_revision = '003_add_preferred_closing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create screening_answers table
    op.create_table(
        'screening_answers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('application_id', sa.String(36), sa.ForeignKey('applications.id', ondelete='SET NULL'), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('question_type', sa.String(50), nullable=True),
        sa.Column('job_title', sa.String(500), nullable=True),
        sa.Column('job_skills', sa.Text(), nullable=True),
        sa.Column('question_embedding', Vector(1536), nullable=True),
        sa.Column('answer_embedding', Vector(1536), nullable=True),
        sa.Column('was_successful', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create HNSW indexes for screening_answers embeddings
    op.execute('''
        CREATE INDEX ix_screening_answers_question_embedding_hnsw
        ON screening_answers
        USING hnsw (question_embedding vector_cosine_ops)
    ''')
    op.execute('''
        CREATE INDEX ix_screening_answers_answer_embedding_hnsw
        ON screening_answers
        USING hnsw (answer_embedding vector_cosine_ops)
    ''')

    # Create proposals table
    op.create_table(
        'proposals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('upwork_proposal_id', sa.String(100), nullable=True, unique=True),
        sa.Column('upwork_job_url', sa.String(500), nullable=True),
        sa.Column('cover_letter_text', sa.Text(), nullable=False),
        sa.Column('job_title', sa.String(500), nullable=True),
        sa.Column('job_description_snippet', sa.Text(), nullable=True),
        sa.Column('job_skills', sa.JSON(), nullable=True),
        sa.Column('job_budget', sa.String(100), nullable=True),
        sa.Column('job_category', sa.String(200), nullable=True),
        sa.Column('bid_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('bid_type', sa.String(20), nullable=True),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('was_hired', sa.Boolean(), nullable=True),
        sa.Column('client_responded', sa.Boolean(), nullable=True),
        sa.Column('earnings', sa.Numeric(10, 2), nullable=True),
        sa.Column('source', sa.String(50), server_default='manual'),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create HNSW index for proposals embedding
    op.execute('''
        CREATE INDEX ix_proposals_embedding_hnsw
        ON proposals
        USING hnsw (embedding vector_cosine_ops)
    ''')


def downgrade() -> None:
    op.drop_index('ix_proposals_embedding_hnsw', table_name='proposals')
    op.drop_table('proposals')
    op.drop_index('ix_screening_answers_answer_embedding_hnsw', table_name='screening_answers')
    op.drop_index('ix_screening_answers_question_embedding_hnsw', table_name='screening_answers')
    op.drop_table('screening_answers')
