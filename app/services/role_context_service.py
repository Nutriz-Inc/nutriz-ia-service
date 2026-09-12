import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import backend_client
from app.services.eva_prompt import (
    _format_dashboard_as_context,
    _format_jobs_as_context,
    _format_routes_as_context,
)
from app.services.step_catalog import nomes_de_etapa

logger = logging.getLogger(__name__)


async def _contexto_do_adm(token: str) -> list[str]:
    dados = await backend_client.fetch_dashboard(token)
    bloco = _format_dashboard_as_context(dados)
    if bloco is None:
        return [
            "INDICADORES DA OPERACAO: nao foi possivel ler os indicadores agora. "
            "Diga que o painel tem os numeros atualizados; nao estime nenhum valor."
        ]
    return [bloco]


async def _contexto_da_enfermeira(db: AsyncSession, token: str) -> list[str]:
    jobs = await backend_client.fetch_jobs(token)
    etapas = await nomes_de_etapa(db, [str(job.get("id_step")) for job in jobs])
    return [_format_jobs_as_context(jobs, etapas)]


async def _contexto_do_motorista(token: str, user_id: str) -> list[str]:
    rotas = await backend_client.fetch_routes(token, user_id)
    paradas: list[dict] = []
    if rotas:
        paradas = await backend_client.fetch_route_stops(token, str(rotas[0]["id_route"]))
    return [_format_routes_as_context(rotas, paradas)]


async def get_role_context(
    db: AsyncSession,
    user_type: str,
    user_id: str,
    token: str,
) -> list[str]:
    try:
        if user_type == "adm":
            return await _contexto_do_adm(token)
        if user_type == "nurse":
            return await _contexto_da_enfermeira(db, token)
        if user_type == "driver":
            return await _contexto_do_motorista(token, user_id)
    except Exception:
        logger.exception(
            f"Falha ao montar o contexto do papel {user_type}; "
            "a EVA segue sem esses dados"
        )
        return []

    return []
