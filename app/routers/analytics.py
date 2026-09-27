import time
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.analytics import consultas
from app.services.analytics.periodo import hoje_em_brasilia, resolver_periodo
from app.services.auth import get_current_user_id
from app.services.profile_service import get_user_type

router = APIRouter(prefix="/analytics", tags=["analytics"])

VALIDADE_DO_CACHE_SEGUNDOS = 60.0

Consulta = Literal[
    "visao_geral",
    "cadeia_fria",
    "logistica",
    "funil_doadora",
    "desempenho_motoristas",
    "desempenho_enfermagem",
    "regioes",
    "alertas",
    "operacao_agora",
    "agenda",
]

_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}


async def exigir_adm(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> str:
    if await get_user_type(db, user_id) != "adm":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Indicadores operacionais sao exclusivos da administracao",
        )
    return user_id


async def _executar(
    db: AsyncSession,
    consulta: str,
    periodo: str | None,
    inicio: date | None,
    fim: date | None,
    agrupar_por: str,
    dia: date | None = None,
    ignorar: str | None = None,
) -> dict[str, Any]:
    if consulta == "agenda":
        return await consultas.agenda_do_dia(db, dia or hoje_em_brasilia(), ignorar)
    if consulta == "alertas":
        return await consultas.alertas(db)
    if consulta == "operacao_agora":
        return await consultas.operacao_agora(db)

    recorte = resolver_periodo(periodo, inicio, fim)
    if consulta == "regioes":
        return await consultas.regioes(db, recorte, agrupar_por)
    return await getattr(consultas, consulta)(db, recorte)


@router.get("/{consulta}")
async def ler_indicador(
    consulta: Consulta,
    periodo: str | None = Query(default=None, max_length=30),
    inicio: date | None = None,
    fim: date | None = None,
    agrupar_por: Literal["cidade", "bairro"] = "cidade",
    data: date | None = None,
    ignorar: str | None = Query(default=None, max_length=36),
    _: str = Depends(exigir_adm),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if consulta == "agenda":
        return await _executar(db, consulta, None, None, None, agrupar_por, data, ignorar)

    chave = (consulta, periodo, inicio, fim, agrupar_por)
    agora = time.monotonic()
    guardado = _cache.get(chave)
    if guardado and agora - guardado[0] < VALIDADE_DO_CACHE_SEGUNDOS:
        return guardado[1]

    dados = await _executar(db, consulta, periodo, inicio, fim, agrupar_por)
    _cache[chave] = (agora, dados)
    return dados
