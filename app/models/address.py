# Modelo espelhado da tabela "address" do backend Go.
# READ-ONLY no Python. Nunca escrever, apenas ler.

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Address(Base):
    __tablename__ = "address"

    id_address: Mapped[str] = mapped_column(String(36), primary_key=True)
    id_user: Mapped[str | None] = mapped_column(String(36), nullable=True)
    id_donation_point: Mapped[str | None] = mapped_column(String(36), nullable=True)
    zipcode: Mapped[str] = mapped_column(String(10), nullable=False)
    street: Mapped[str] = mapped_column(String(150), nullable=False)
    number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    neighborhood: Mapped[str] = mapped_column(String(100), nullable=False)
    complement: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(precision=10, scale=7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(precision=10, scale=7), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    removed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
