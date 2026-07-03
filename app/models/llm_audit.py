import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LlmAudit(Base):
    __tablename__ = "llm_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    prompt_full: Mapped[dict[str, Any] | list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    chunks_used: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    llm_provider: Mapped[str] = mapped_column(String(30), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(50), nullable=False)
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Modo publico: registros anonimos nao tem user_id; a sessao e o IP
    # (apenas hasheado, nunca em claro) sao a unica rastreabilidade LGPD.
    is_anonymous: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
