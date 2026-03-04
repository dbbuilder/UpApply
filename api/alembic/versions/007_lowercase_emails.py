"""Normalize all user emails to lowercase; remove empty duplicate uppercase accounts.

Revision ID: 007_lowercase_emails
Revises: 006_add_beta_feedback
Create Date: 2026-03-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '007_lowercase_emails'
down_revision: Union[str, None] = '006_add_beta_feedback'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Delete uppercase-only accounts that are empty duplicates of a lowercase account.
    #    "Empty" = no memories and profile has no real data.
    op.execute(sa.text("""
        DELETE FROM users
        WHERE email != LOWER(email)
          AND EXISTS (
              SELECT 1 FROM users u2
              WHERE LOWER(u2.email) = LOWER(users.email)
                AND u2.email = LOWER(u2.email)
          )
          AND NOT EXISTS (SELECT 1 FROM memories m WHERE m.user_id = users.id)
          AND NOT EXISTS (SELECT 1 FROM proposals p WHERE p.user_id = users.id)
          AND NOT EXISTS (
              SELECT 1 FROM user_profiles up
              WHERE up.user_id = users.id
                AND (up.full_name IS NOT NULL
                  OR up.professional_title IS NOT NULL
                  OR up.career_goals IS NOT NULL
                  OR up.skills IS NOT NULL)
          )
    """))

    # 2. Lowercase any remaining mixed-case emails (no lowercase duplicate exists).
    op.execute(sa.text("""
        UPDATE users SET email = LOWER(email) WHERE email != LOWER(email)
    """))


def downgrade() -> None:
    # Emails that were lowercased cannot be reversed (original casing is unknown).
    pass
