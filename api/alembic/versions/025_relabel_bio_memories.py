"""Relabel Chris's curated bio memories from 'chatgpt_corpus' to 'bio_import'.

They were seeded by the corpus importer before sources were split, so /facts/from-memories
(trusted sources only) skips them. Data-only, scoped to one account and the 14 curated titles
in scripts/chris_bio_memories.json; a no-op on any other database.

Revision ID: 025_relabel_bio_memories
Revises: 024_refine_loop
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = '025_relabel_bio_memories'
down_revision = '024_refine_loop'
branch_labels = None
depends_on = None

EMAIL = 'chris@servicevision.net'
TITLES = (
    'Stratavault.ai — Private enterprise AI knowledge base with RAG and PII protection',
    'AestheticIQ.ai — AI business intelligence SaaS for medical spas',
    'AnalyzeMyCloud.com — AI-powered cloud cost optimization service',
    'Remote2Me.com — Enterprise zero-trust remote control platform',
    'FireProofApp.net — Fire extinguisher inspection and compliance SaaS',
    'Migrated 160-server datacenter to Azure hybrid cloud',
    'SaaS company founded 2001 — 25+ years enterprise software',
    'K-12 education SaaS platform — 20+ years operating, 3,000 clients',
    'UpApply — AI-powered Upwork proposal automation',
    'ServiceVision.net — Technology consulting and AI integration',
    'Multi-tenant SaaS architecture: 3,000 per-client SQL Server databases',
    'SQL Server expert: stored procedures, CTEs, indexing, replication',
    'Azure cloud architect: App Service, Functions, Front Door, Key Vault, DevOps',
    'Upwork proposal style and tone preferences',
)

_RELABEL = sa.text("""
    UPDATE memories m SET source = :to_source
      FROM users u
     WHERE u.id = m.user_id AND u.email = :email
       AND m.source = :from_source
       AND m.title IN :titles
""").bindparams(sa.bindparam('titles', expanding=True))


def upgrade() -> None:
    op.get_bind().execute(_RELABEL, {
        'email': EMAIL, 'from_source': 'chatgpt_corpus', 'to_source': 'bio_import', 'titles': list(TITLES),
    })


def downgrade() -> None:
    op.get_bind().execute(_RELABEL, {
        'email': EMAIL, 'from_source': 'bio_import', 'to_source': 'chatgpt_corpus', 'titles': list(TITLES),
    })
