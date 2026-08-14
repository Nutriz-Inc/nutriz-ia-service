"""llm_audit ganha action_emitted (acao contextual enviada na resposta)

Registra o slug da acao deterministica emitida junto da resposta da EVA
(signup, whatsapp, collection_points, articles) ou NULL quando nenhuma acao
foi disparada. Permite medir conversao depois. Nao altera registros antigos.

Revision ID: d4e91a7c22b0
Revises: c9e42f1b83a7
Create Date: 2026-07-29

"""
import sqlalchemy as sa
from alembic import op


revision = "d4e91a7c22b0"
down_revision = "c9e42f1b83a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_audit",
        sa.Column("action_emitted", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_audit", "action_emitted")
