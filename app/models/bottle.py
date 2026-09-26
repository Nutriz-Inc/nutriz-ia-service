from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Bottle(Base):
    __tablename__ = "bottle"

    id_bottle: Mapped[str] = mapped_column(String(36), primary_key=True)
    id_donation: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quantity_donated_ml: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2), nullable=True
    )
    discarded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
