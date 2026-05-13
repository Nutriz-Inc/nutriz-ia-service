# Modelo espelhado da tabela "consent_log" do backend Go.
# READ-ONLY no Python. Nunca escrever, apenas ler.

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConsentLog(Base):
    __tablename__ = "consent_log"

    id_consent_log: Mapped[str] = mapped_column(String(36), primary_key=True)
    id_user: Mapped[str] = mapped_column(String(36), nullable=False)
    terms_version: Mapped[str] = mapped_column(String(50), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)
