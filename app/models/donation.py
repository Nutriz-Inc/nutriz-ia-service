# Modelos espelhados das tabelas de doacao do backend Go.
# READ-ONLY no Python. Nunca escrever, apenas ler.
#
# MIRROR MINIMO: sao mapeadas APENAS as colunas efetivamente lidas pelo contexto
# da EVA. O ORM coloca no SELECT toda coluna mapeada, entao mapear uma coluna que
# nao existe no banco real do Go quebra a query em producao (foi o que aconteceu
# com address.updated_by). O repo do Go tambem pode estar atras do banco real
# (o front ja usa donation.score_feedback, que nao esta nas migrations), entao
# quanto menor a superficie mapeada, menor o risco de divergencia.
#
# Colunas deliberadamente NAO mapeadas por risco de conteudo clinico:
# - donation_step.description  (texto livre de adm: sorologia, motivo de inaptidao)
# - donation.user_feedback     (texto livre da nutriz)
# A tabela donation_step_timeline e a tabela job nao sao espelhadas pelo mesmo
# motivo (toda linha carrega descricao livre).

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Donation(Base):
    __tablename__ = "donation"

    id_donation: Mapped[str] = mapped_column(String(36), primary_key=True)
    # ATENCAO: a tabela donation NAO tem id_user. O dono da doacao e created_by
    # (mesma regra do backend Go em ListDonationByFilters e no gate do GetDonation).
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quantity_donated: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DonationStep(Base):
    __tablename__ = "donation_step"

    id_donation_step: Mapped[str] = mapped_column(String(36), primary_key=True)
    id_donation: Mapped[str] = mapped_column(String(36), nullable=False)
    id_address: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # name e status sao ENUMs no Postgres do Go; mapeados como String porque o
    # asyncpg entrega o valor do enum como str e o tipo nativo nao acrescenta
    # nada na leitura (mesma escolha ja feita em messages.role).
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    set_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DonationPoint(Base):
    __tablename__ = "donation_point"

    id_donation_point: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
