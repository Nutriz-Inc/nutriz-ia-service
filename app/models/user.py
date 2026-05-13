# Modelo espelhado da tabela "user" do backend Go.
# READ-ONLY no Python. Nunca escrever, apenas ler.

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "user"

    id_user: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cpf: Mapped[str] = mapped_column(String(11), unique=True, nullable=False)
    birth_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    milk_donated: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    removed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
