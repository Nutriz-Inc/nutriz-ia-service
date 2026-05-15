# Servico de validacao de consentimento LGPD.
# Verifica se a nutriz tem registro em consent_log (tabela append-only do go).
# Bloqueia chat se nao houver consentimento valido.

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConsentLog


logger = logging.getLogger(__name__)


async def has_valid_consent(db: AsyncSession, id_user: str) -> bool:
    result = await db.execute(
        select(ConsentLog.id_consent_log)
        .where(ConsentLog.id_user == id_user)
        .order_by(ConsentLog.accepted_at.desc())
        .limit(1)
    )
    consent = result.scalar_one_or_none()
    has_consent = consent is not None
    if not has_consent:
        logger.warning(f"Tentativa de chat sem consentimento LGPD: id_user={id_user}")
    return has_consent


async def get_latest_consent_version(db: AsyncSession, id_user: str) -> str | None:
    result = await db.execute(
        select(ConsentLog.terms_version)
        .where(ConsentLog.id_user == id_user)
        .order_by(ConsentLog.accepted_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
