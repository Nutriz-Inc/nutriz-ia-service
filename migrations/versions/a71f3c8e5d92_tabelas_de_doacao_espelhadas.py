"""tabelas de doacao espelhadas (donation, donation_step, donation_point)

Revision ID: a71f3c8e5d92
Revises: d4e91a7c22b0
Create Date: 2026-08-18 10:12:00.000000

Estas tabelas sao de PROPRIEDADE DO BACKEND GO. O IA service so le. A migration
existe para o ambiente de dev, onde o banco do compose nasce vazio e nao roda as
migrations do Go.

Por isso tudo aqui e CREATE TABLE IF NOT EXISTS: em um banco compartilhado, onde
as migrations do Go ja rodaram, esta revision e inofensiva (nao recria nada, nao
altera nada). O downgrade nao derruba as tabelas - dropar tabela de outro servico
a partir daqui seria destrutivo demais.

Diferenca proposital em relacao ao Go: name/status ficam como VARCHAR em vez dos
enums enum_donation_steps/enum_donation_step_status. O ORM le os dois do mesmo
jeito (o asyncpg entrega enum como str) e o dev nao precisa dos tipos.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a71f3c8e5d92"
down_revision: Union[str, None] = "d4e91a7c22b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS donation_point (
            id_donation_point VARCHAR(36) PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            description TEXT,
            has_home BOOLEAN NOT NULL DEFAULT false,
            phone_number VARCHAR(20),
            email VARCHAR(255),
            opening_hours VARCHAR(255),
            removed_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS donation (
            id_donation VARCHAR(36) PRIMARY KEY,
            quantity_donated NUMERIC(10,2),
            is_active BOOLEAN NOT NULL,
            user_feedback TEXT,
            created_at TIMESTAMP NOT NULL,
            created_by VARCHAR(36) NOT NULL,
            updated_at TIMESTAMP,
            updated_by VARCHAR(36),
            removed_at TIMESTAMP,
            removed_by VARCHAR(36)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS donation_step (
            id_donation_step VARCHAR(36) PRIMARY KEY,
            id_donation VARCHAR(36) NOT NULL,
            id_address VARCHAR(36),
            name VARCHAR(50) NOT NULL,
            description TEXT,
            status VARCHAR(20) NOT NULL,
            set_date TIMESTAMP,
            created_at TIMESTAMP NOT NULL,
            created_by VARCHAR(36),
            updated_at TIMESTAMP,
            updated_by VARCHAR(36),
            completed_at TIMESTAMP
        )
        """
    )
    # A doacao da nutriz e localizada por created_by (a tabela nao tem id_user).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_donation_created_by ON donation (created_by)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_donation_step_id_donation "
        "ON donation_step (id_donation)"
    )


def downgrade() -> None:
    # So os indices criados por esta revision. As tabelas pertencem ao Go e
    # podem conter dados de producao - nao sao dropadas aqui.
    op.execute("DROP INDEX IF EXISTS ix_donation_step_id_donation")
    op.execute("DROP INDEX IF EXISTS ix_donation_created_by")
