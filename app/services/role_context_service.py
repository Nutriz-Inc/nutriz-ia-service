import asyncio
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import backend_client
from app.services.eva_prompt import (
    _format_dashboard_as_context,
    _format_jobs_as_context,
    _format_routes_as_context,
    rota_em_foco,
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
    hoje = date.today().isoformat()
    pendentes, do_dia = await asyncio.gather(
        backend_client.fetch_jobs(token, status="pending"),
        backend_client.fetch_jobs(token, date_set=hoje),
    )

    # Sem os de hoje, um agendamento concluido hoje de manha simplesmente nao
    # existiria para a EVA e ela responderia como se ainda estivesse pendente.
    jobs: list[dict] = []
    vistos: set[str] = set()
    for job in [*do_dia, *pendentes]:
        chave = str(job.get("id_job"))
        if chave in vistos:
            continue
        vistos.add(chave)
        jobs.append(job)

    etapas = await nomes_de_etapa(db, [str(job.get("id_step")) for job in jobs])
    return [_format_jobs_as_context(jobs, etapas)]


async def _contexto_do_motorista(token: str, user_id: str) -> list[str]:
    rotas = await backend_client.fetch_routes(token, user_id)
    foco = rota_em_foco(rotas)

    paradas: list[dict] = []
    if foco is not None:
        paradas = await backend_client.fetch_route_stops(
            token, str(foco.get("id_route"))
        )

    return [_format_routes_as_context(rotas, foco, paradas)]


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
