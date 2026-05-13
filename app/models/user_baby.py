# Modelo espelhado da tabela "user_baby" do backend Go.
# READ-ONLY no Python. Nunca escrever, apenas ler.

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserBaby(Base):
    __tablename__ = "user_baby"

    id_user_baby: Mapped[str] = mapped_column(String(36), primary_key=True)
    id_user: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    birth_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
