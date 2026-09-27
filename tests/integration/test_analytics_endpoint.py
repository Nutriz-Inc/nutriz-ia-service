from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text

from app.routers import analytics
from tests.conftest import make_token


@pytest.fixture(autouse=True)
def limpar_cache():
    analytics._cache.clear()
    yield
    analytics._cache.clear()


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _usuario(db_session, id_user: str, tipo: str) -> str:
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    await db_session.execute(
        text(
            'INSERT INTO "user" (id_user, type, name, cpf, birth_date, phone_number, '
            "email, password, created_at, created_by) VALUES "
            "(:id, :tipo, 'Pessoa', :cpf, :nasc, :tel, :email, 'x', :agora, :id)"
        ),
        {
            "id": id_user,
            "tipo": tipo,
            "cpf": f"{abs(hash(id_user)) % 10**11:011d}",
            "nasc": agora - timedelta(days=9000),
            "tel": f"11{abs(hash(tipo)) % 10**9:09d}",
            "email": f"{id_user}@x.com",
            "agora": agora,
        },
    )
    await db_session.commit()
    return make_token(user_id=id_user)


async def test_sem_token_devolve_401(app_with_overrides):
    async with _client(app_with_overrides) as client:
        resposta = await client.get("/analytics/visao_geral")
    assert resposta.status_code == 401


@pytest.mark.parametrize("tipo", ["common", "nurse", "driver"])
async def test_quem_nao_e_adm_recebe_403(app_with_overrides, db_session, tipo):
    token = await _usuario(db_session, f"u-{tipo}", tipo)
    async with _client(app_with_overrides) as client:
        resposta = await client.get(
            "/analytics/visao_geral", headers={"Authorization": f"Bearer {token}"}
        )
    assert resposta.status_code == 403


async def test_adm_le_indicadores_e_operacao_agora(app_with_overrides, db_session):
    token = await _usuario(db_session, "u-adm", "adm")
    cabecalho = {"Authorization": f"Bearer {token}"}
    async with _client(app_with_overrides) as client:
        visao = await client.get("/analytics/visao_geral?periodo=tudo", headers=cabecalho)
        agora = await client.get("/analytics/operacao_agora", headers=cabecalho)

    assert visao.status_code == 200
    assert visao.json()["periodo"]["rotulo"] == "todo o histórico"
    assert agora.status_code == 200
    assert "rotas_em_andamento" in agora.json()


async def test_consulta_desconhecida_devolve_422(app_with_overrides, db_session):
    token = await _usuario(db_session, "u-adm", "adm")
    async with _client(app_with_overrides) as client:
        resposta = await client.get(
            "/analytics/senhas", headers={"Authorization": f"Bearer {token}"}
        )
    assert resposta.status_code == 422


async def test_adm_le_a_agenda_do_dia_sem_cache(app_with_overrides, db_session):
    token = await _usuario(db_session, "u-adm", "adm")
    async with _client(app_with_overrides) as client:
        resposta = await client.get(
            "/analytics/agenda?data=2026-10-05",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["data"] == "2026-10-05"
    assert dados["capacidade_por_horario"] == 3
    assert analytics._cache == {}
