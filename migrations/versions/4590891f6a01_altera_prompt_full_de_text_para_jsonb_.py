"""altera prompt_full de text para jsonb em llm_audit

Revision ID: 4590891f6a01
Revises: ea59d6d81ae9
Create Date: 2026-05-13 19:09:26.573049

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4590891f6a01'
down_revision: Union[str, None] = 'ea59d6d81ae9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'llm_audit',
        'prompt_full',
        existing_type=sa.TEXT(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
        postgresql_using='prompt_full::jsonb',
    )


def downgrade() -> None:
    op.alter_column(
        'llm_audit',
        'prompt_full',
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.TEXT(),
        existing_nullable=False,
        postgresql_using='prompt_full::text',
    )
