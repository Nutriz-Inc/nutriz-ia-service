# TODO Leo: schema espelhado da tabela users do backend Go.
# Confirmar com o Leo: campos exatos, tipos, nomes (PT ou EN).
# Este modelo é READ-ONLY no Python. Nunca escrever, apenas ler.

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    cep: Mapped[str | None] = mapped_column(String(9), nullable=True)
    data_nascimento_bebe: Mapped[date | None] = mapped_column(Date, nullable=True)
    consent_lgpd_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
