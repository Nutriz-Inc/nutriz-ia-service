import asyncio
import logging
import time

from sqlalchemy import text

from app.database import engine
from app.llm.provider import get_llm_provider

logger = logging.getLogger(__name__)

LIMITE_SEGUNDOS = 15.0


async def _aquecer_banco() -> None:
    async with engine.connect() as conexao:
        await conexao.execute(text("SELECT 1"))


async def _medir(nome: str, tarefa) -> None:
    inicio = time.perf_counter()
    try:
        await asyncio.wait_for(tarefa, timeout=LIMITE_SEGUNDOS)
    except Exception as erro:
        logger.warning(f"Aquecimento de {nome} falhou: {type(erro).__name__}")
        return
    logger.info(f"{nome} aquecido em {(time.perf_counter() - inicio) * 1000:.0f}ms")


async def aquecer_dependencias() -> None:
    await asyncio.gather(
        _medir("banco", _aquecer_banco()),
        _medir("llm", get_llm_provider().aquecer()),
    )
