"""Knowledge layer: facts table, voice-sample columns on proposals, memory retrieval flag.

Revision ID: 022_knowledge_layer
Revises: 021_global_signal_pool
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from pgvector.sqlalchemy import Vector

revision = '022_knowledge_layer'
down_revision = '021_global_signal_pool'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'facts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('statement', sa.Text(), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('skills', ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('industries', ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('job_types', ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('strength', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('status', sa.String(20), nullable=False, server_default='candidate'),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_ref', sa.String(200), nullable=True),
        sa.Column('sources', JSONB(), nullable=False, server_default='[]'),
        sa.Column('times_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('times_in_won', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_facts_user_id', 'facts', ['user_id'])
    op.create_index('ix_facts_user_status', 'facts', ['user_id', 'status'])
    op.execute(
        "CREATE INDEX ix_facts_embedding_hnsw ON facts "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # Voice samples = proposals + author/outcome/job context
    op.add_column('proposals', sa.Column('author', sa.String(20), nullable=False, server_default='chris'))
    op.add_column('proposals', sa.Column('outcome', sa.String(20), nullable=True))
    op.add_column('proposals', sa.Column('job_text', sa.Text(), nullable=True))
    op.add_column('proposals', sa.Column('screening_answers', JSONB(), nullable=True))
    op.add_column('proposals', sa.Column('job_needs_embedding', Vector(1536), nullable=True))
    op.add_column('proposals', sa.Column('facts_ingested_at', sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "CREATE INDEX ix_proposals_job_needs_embedding_hnsw ON proposals "
        "USING hnsw (job_needs_embedding vector_cosine_ops)"
    )

    op.add_column(
        'memories',
        sa.Column('exclude_from_retrieval', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # --- Data step (flag/re-tag only; nothing is deleted) ---
    # Corpus memories built by scripts/import_chatgpt_corpus.py:build_proposal_memory start
    # with "JOB POSTING:" — they are strangers' job posts, never portfolio evidence.
    op.execute("UPDATE memories SET exclude_from_retrieval = true WHERE content LIKE 'JOB POSTING:%'")
    # Letters created by api/app/api/v1/import_chatgpt.py are ChatGPT-authored.
    op.execute("UPDATE proposals SET author = 'ai' WHERE source = 'chatgpt_import'")
    # Extension-sourced rows started as UpApply drafts (jobs.py submit + applications.py promote).
    op.execute("UPDATE proposals SET author = 'chris_edited_ai' WHERE source = 'extension'")
    # Outcome backfill from legacy flags so voice retrieval can be outcome-weighted.
    # Status drives the outcome. Pre-phase-0 imports stored was_hired=false for open
    # statuses (submitted/viewed/responded/interviewed/active), so was_hired=false alone
    # never means 'declined'; only an explicit declined status does.
    op.execute("UPDATE proposals SET outcome = 'hired' WHERE was_hired = true")
    op.execute(
        "UPDATE proposals SET outcome = 'interviewed' "
        "WHERE outcome IS NULL AND lower(status) LIKE '%interview%'"
    )
    op.execute(
        "UPDATE proposals SET outcome = 'replied' "
        "WHERE outcome IS NULL AND (client_responded = true OR lower(status) IN ('responded', 'active'))"
    )
    op.execute(
        "UPDATE proposals SET outcome = 'viewed' "
        "WHERE outcome IS NULL AND lower(status) = 'viewed'"
    )
    op.execute(
        "UPDATE proposals SET outcome = 'declined' "
        "WHERE outcome IS NULL AND lower(status) LIKE '%declin%'"
    )


def downgrade() -> None:
    op.drop_column('memories', 'exclude_from_retrieval')
    op.execute("DROP INDEX IF EXISTS ix_proposals_job_needs_embedding_hnsw")
    op.drop_column('proposals', 'facts_ingested_at')
    op.drop_column('proposals', 'job_needs_embedding')
    op.drop_column('proposals', 'screening_answers')
    op.drop_column('proposals', 'job_text')
    op.drop_column('proposals', 'outcome')
    op.drop_column('proposals', 'author')
    op.drop_table('facts')
