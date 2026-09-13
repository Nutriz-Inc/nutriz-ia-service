import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None

CAMPOS_ROTA = (
    "id_route",
    "name",
    "status",
    "city",
    "neighborhood",
    "date_set",
    "date_start",
    "date_end",
    "mileage",
    "estimated_time",
)

CAMPOS_PARADA = (
    "id_route_donation_step",
    "id_donation_step",
    "stop_order",
    "status",
    "date_start",
    "date_end",
)

CAMPOS_ENDERECO = (
    "street",
    "number",
    "neighborhood",
    "city",
    "state",
    "zipcode",
)

CAMPOS_JOB = (
    "id_job",
    "id_step",
    "id_donation",
    "status",
    "date_set",
)

CAMPOS_DASHBOARD = (
    "total_milk_collected",
    "bottles_count",
    "discarded_bottles_count",
    "average_bottles_per_donor",
    "bottles_utilization_rate",
    "average_mileage_per_route",
    "average_stops_per_route",
    "average_route_duration_hours",
    "average_service_time_hours",
    "donations_with_error",
    "donor_recurrence_rate",
    "milk_collected_by_month",
    "active_donations_by_step",
)


def _somente(origem: dict[str, Any], campos: tuple[str, ...]) -> dict[str, Any]:
    return {chave: origem.get(chave) for chave in campos if origem.get(chave) is not None}


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.BACKEND_API_URL.rstrip("/"),
            timeout=settings.BACKEND_API_TIMEOUT_SECONDS,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _get(caminho: str, token: str, params: dict[str, Any] | None = None) -> Any:
    resposta = await get_client().get(
        caminho,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
    )
    resposta.raise_for_status()
    return resposta.json()


async def fetch_dashboard(token: str) -> dict[str, Any] | None:
    try:
        dados = await _get("/internal/dashboard", token)
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"Dashboard indisponivel para a EVA: HTTP {e.response.status_code}"
        )
        return None
    except httpx.HTTPError:
        logger.exception("Falha de rede ao buscar o dashboard para a EVA")
        return None

    if not isinstance(dados, dict):
        return None

    return _somente(dados, CAMPOS_DASHBOARD)


async def fetch_jobs(
    token: str,
    page_size: int = 10,
    status: str | None = None,
    date_set: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"page": 1, "page_size": page_size}
    if status:
        params["status"] = status
    if date_set:
        params["date_set"] = date_set

    try:
        dados = await _get("/internal/job", token, params=params)
    except httpx.HTTPStatusError as e:
        logger.warning(f"Jobs indisponiveis para a EVA: HTTP {e.response.status_code}")
        return []
    except httpx.HTTPError:
        logger.exception("Falha de rede ao buscar jobs para a EVA")
        return []

    linhas = dados.get("data") if isinstance(dados, dict) else None
    if not isinstance(linhas, list):
        return []

    return [_somente(linha, CAMPOS_JOB) for linha in linhas if isinstance(linha, dict)]


async def fetch_routes(
    token: str, id_driver: str, page_size: int = 10
) -> list[dict[str, Any]]:
    try:
        dados = await _get(
            "/internal/route",
            token,
            params={"page": 1, "page_size": page_size, "id_driver": id_driver},
        )
    except httpx.HTTPStatusError as e:
        logger.warning(f"Rotas indisponiveis para a EVA: HTTP {e.response.status_code}")
        return []
    except httpx.HTTPError:
        logger.exception("Falha de rede ao buscar rotas para a EVA")
        return []

    linhas = dados.get("data") if isinstance(dados, dict) else None
    if not isinstance(linhas, list):
        return []

    return [_somente(linha, CAMPOS_ROTA) for linha in linhas if isinstance(linha, dict)]


async def fetch_route_stops(token: str, id_route: str) -> list[dict[str, Any]]:
    try:
        dados = await _get(f"/internal/route/{id_route}", token)
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"Paradas indisponiveis para a EVA: HTTP {e.response.status_code}"
        )
        return []
    except httpx.HTTPError:
        logger.exception("Falha de rede ao buscar paradas para a EVA")
        return []

    paradas = dados.get("stops") if isinstance(dados, dict) else None
    if not isinstance(paradas, list):
        return []

    limpas = []
    for parada in paradas:
        if not isinstance(parada, dict):
            continue
        limpa = _somente(parada, CAMPOS_PARADA)
        endereco = parada.get("address")
        if isinstance(endereco, dict):
            limpa["address"] = _somente(endereco, CAMPOS_ENDERECO)
        limpas.append(limpa)

    return limpas
