import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DonationStep

logger = logging.getLogger(__name__)


async def nomes_de_etapa(db: AsyncSession, ids: list[str]) -> dict[str, str]:
    unicos = [id_etapa for id_etapa in dict.fromkeys(ids) if id_etapa]
    if not unicos:
        return {}

    try:
        resultado = await db.execute(
            select(DonationStep.id_donation_step, DonationStep.name).where(
                DonationStep.id_donation_step.in_(unicos)
            )
        )
        return {linha[0]: linha[1] for linha in resultado.all()}
    except Exception:
        logger.exception("Falha ao ler nomes de etapa; seguindo sem eles")
        await db.rollback()
        return {}
