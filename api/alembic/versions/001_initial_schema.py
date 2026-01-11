"""Initial schema with all tables

Revision ID: 001_initial
Revises:
Create Date: 2025-01-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_verified', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # User Profiles table
    op.create_table(
        'user_profiles',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),

        # Identity
        sa.Column('full_name', sa.String(255)),
        sa.Column('professional_title', sa.String(255)),
        sa.Column('headline', sa.Text()),
        sa.Column('bio', sa.Text()),

        # Resume data
        sa.Column('resume_text', sa.Text()),
        sa.Column('skills', sa.JSON()),
        sa.Column('work_history', sa.JSON()),
        sa.Column('education', sa.JSON()),
        sa.Column('certifications', sa.JSON()),
        sa.Column('portfolio_links', sa.JSON()),

        # Goals & Aspirations
        sa.Column('career_goals', sa.Text()),
        sa.Column('ideal_project_description', sa.Text()),
        sa.Column('skills_to_highlight', sa.JSON()),
        sa.Column('skills_to_develop', sa.JSON()),

        # Project Preferences
        sa.Column('preferred_project_types', sa.JSON()),
        sa.Column('preferred_industries', sa.JSON()),
        sa.Column('preferred_team_size', sa.String(50)),
        sa.Column('preferred_client_types', sa.JSON()),
        sa.Column('project_duration_preference', sa.String(50)),

        # Deal Breakers
        sa.Column('avoid_keywords', sa.JSON()),
        sa.Column('avoid_industries', sa.JSON()),
        sa.Column('minimum_budget', sa.Numeric(10, 2)),
        sa.Column('minimum_hourly_rate', sa.Numeric(10, 2)),
        sa.Column('red_flag_patterns', sa.JSON()),

        # Communication & Style
        sa.Column('tone_preference', sa.String(50)),
        sa.Column('communication_style', sa.Text()),
        sa.Column('response_time_expectation', sa.String(100)),
        sa.Column('timezone', sa.String(50)),
        sa.Column('working_hours_preference', sa.Text()),

        # Unique Value Props
        sa.Column('unique_strengths', sa.JSON()),
        sa.Column('success_stories', sa.JSON()),
        sa.Column('client_testimonial_themes', sa.JSON()),

        # Pricing
        sa.Column('hourly_rate_min', sa.Numeric(10, 2)),
        sa.Column('hourly_rate_max', sa.Numeric(10, 2)),
        sa.Column('hourly_rate_preferred', sa.Numeric(10, 2)),
        sa.Column('fixed_price_minimum', sa.Numeric(10, 2)),
        sa.Column('pricing_flexibility', sa.Text()),

        # Availability
        sa.Column('hours_per_week_available', sa.Integer()),
        sa.Column('availability_start_date', sa.Date()),
        sa.Column('currently_accepting_work', sa.Boolean(), default=True),

        # Setup tracking
        sa.Column('setup_completed', sa.Boolean(), default=False),
        sa.Column('setup_step', sa.Integer()),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_user_profiles_user_id', 'user_profiles', ['user_id'])

    # Memories table with vector embedding
    op.create_table(
        'memories',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('category', sa.String(50)),

        sa.Column('skills_demonstrated', sa.JSON()),
        sa.Column('industry', sa.String(100)),
        sa.Column('project_type', sa.String(100)),
        sa.Column('client_type', sa.String(100)),

        sa.Column('outcome', sa.Text()),
        sa.Column('metrics', sa.JSON()),
        sa.Column('client_feedback', sa.Text()),

        sa.Column('embedding', Vector(1536)),

        sa.Column('source', sa.String(50)),
        sa.Column('importance_score', sa.Numeric(3, 2), default=0.5),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_memories_user_id', 'memories', ['user_id'])

    # Create HNSW index for vector similarity search
    op.execute('''
        CREATE INDEX memories_embedding_idx ON memories
        USING hnsw (embedding vector_cosine_ops)
    ''')

    # Jobs table
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

        sa.Column('upwork_job_id', sa.String(100)),
        sa.Column('upwork_url', sa.String(500), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),

        sa.Column('budget_type', sa.String(20)),
        sa.Column('budget_amount', sa.String(100)),
        sa.Column('budget_min', sa.Numeric(10, 2)),
        sa.Column('budget_max', sa.Numeric(10, 2)),

        sa.Column('skills_required', sa.JSON()),
        sa.Column('experience_level', sa.String(50)),
        sa.Column('project_length', sa.String(100)),

        sa.Column('client_info', sa.JSON()),

        sa.Column('embedding', Vector(1536)),
        sa.Column('match_score', sa.Numeric(5, 2)),
        sa.Column('analysis', sa.JSON()),

        sa.Column('posted_date', sa.DateTime(timezone=True)),
        sa.Column('scraped_at', sa.DateTime(timezone=True)),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_jobs_user_id', 'jobs', ['user_id'])
    op.create_index('ix_jobs_upwork_url', 'jobs', ['upwork_url'])

    # Cover Letters table
    op.create_table(
        'cover_letters',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),

        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('model_used', sa.String(100)),
        sa.Column('memories_used', sa.JSON()),
        sa.Column('version', sa.Integer(), default=1),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_cover_letters_user_id', 'cover_letters', ['user_id'])
    op.create_index('ix_cover_letters_job_id', 'cover_letters', ['job_id'])

    # Applications table
    op.create_table(
        'applications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('cover_letter_id', sa.String(36), sa.ForeignKey('cover_letters.id', ondelete='SET NULL')),

        sa.Column('status', sa.String(20), default='draft'),
        sa.Column('bid_amount', sa.Numeric(10, 2)),

        sa.Column('outcome_notes', sa.Text()),
        sa.Column('client_response', sa.Text()),
        sa.Column('earnings', sa.Numeric(10, 2)),

        sa.Column('submitted_at', sa.DateTime(timezone=True)),
        sa.Column('responded_at', sa.DateTime(timezone=True)),
        sa.Column('outcome_recorded_at', sa.DateTime(timezone=True)),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_applications_user_id', 'applications', ['user_id'])
    op.create_index('ix_applications_job_id', 'applications', ['job_id'])

    # Feedback table
    op.create_table(
        'feedback',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('application_id', sa.String(36), sa.ForeignKey('applications.id', ondelete='CASCADE')),
        sa.Column('cover_letter_id', sa.String(36), sa.ForeignKey('cover_letters.id', ondelete='CASCADE')),

        sa.Column('feedback_type', sa.String(50), nullable=False),
        sa.Column('rating', sa.Integer()),
        sa.Column('comment', sa.Text()),

        sa.Column('original_text', sa.Text()),
        sa.Column('edited_text', sa.Text()),

        sa.Column('was_helpful', sa.Boolean()),
        sa.Column('would_use_again', sa.Boolean()),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_feedback_user_id', 'feedback', ['user_id'])


def downgrade() -> None:
    op.drop_table('feedback')
    op.drop_table('applications')
    op.drop_table('cover_letters')
    op.drop_table('jobs')
    op.execute('DROP INDEX IF EXISTS memories_embedding_idx')
    op.drop_table('memories')
    op.drop_table('user_profiles')
    op.drop_table('users')
    op.execute('DROP EXTENSION IF EXISTS vector')
