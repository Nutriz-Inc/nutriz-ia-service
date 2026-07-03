"""llm_audit ganha campos para auditoria anonima (modo publico)

Registros de chat anonimo nao tem id_user. A rastreabilidade LGPD passa a
ser feita por session_id + ip_hash (hash do IP, nunca o IP em claro).
user_id ja era logicamente nullable no model.

Revision ID: c9e42f1b83a7
Revises: b7c31a9f02d4
Create Date: 2026-07-03

"""
import sqlalchemy as sa
from alembic import op


revision = "c9e42f1b83a7"
down_revision = "b7c31a9f02d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_audit",
        sa.Column(
            "is_anonymous",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "llm_audit",
        sa.Column("session_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "llm_audit",
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_llm_audit_session_id", "llm_audit", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_llm_audit_session_id", table_name="llm_audit")
    op.drop_column("llm_audit", "ip_hash")
    op.drop_column("llm_audit", "session_id")
    op.drop_column("llm_audit", "is_anonymous")
