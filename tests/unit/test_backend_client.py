import httpx
import pytest

from app.services import backend_client


@pytest.fixture(autouse=True)
def limpa_cliente():
    backend_client._client = None
    yield
    backend_client._client = None


def monta_cliente(handler) -> None:
    backend_client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://backend-de-teste",
    )


class TestDashboard:
    async def test_devolve_somente_campos_agregados(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "total_milk_collected": 12450,
                    "bottles_count": 320,
                    "donor_recurrence_rate": 0.62,
                    "nome_da_doadora": "Maria Ribeiro",
                    "cpf": "12345678900",
                },
            )

        monta_cliente(handler)
        dados = await backend_client.fetch_dashboard("tok")

        assert dados["total_milk_collected"] == 12450
        assert "nome_da_doadora" not in dados
        assert "cpf" not in dados

    async def test_manda_o_token_no_header(self):
        capturado = {}

        def handler(request: httpx.Request) -> httpx.Response:
            capturado["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"total_milk_collected": 1})

        monta_cliente(handler)
        await backend_client.fetch_dashboard("tok-do-usuario")

        assert capturado["auth"] == "Bearer tok-do-usuario"

    async def test_403_nao_derruba_e_devolve_none(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"message": "forbidden"})

        monta_cliente(handler)
        assert await backend_client.fetch_dashboard("tok") is None

    async def test_erro_de_rede_devolve_none(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("sem rede")

        monta_cliente(handler)
        assert await backend_client.fetch_dashboard("tok") is None


class TestJobs:
    async def test_descarta_texto_livre_com_teor_clinico(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id_job": "job-1",
                            "id_step": "step-1",
                            "status": "pending",
                            "date_set": "2026-09-11T10:00:00Z",
                            "name": "Coletar leite - sorologia reagente",
                            "description": "doadora inapta, encaminhar",
                            "user_feedback": "relato clinico",
                            "user_common_name": "Maria Ribeiro",
                        }
                    ],
                    "total": 1,
                },
            )

        monta_cliente(handler)
        jobs = await backend_client.fetch_jobs("tok")

        assert len(jobs) == 1
        assert jobs[0]["id_job"] == "job-1"
        assert "description" not in jobs[0]
        assert "user_feedback" not in jobs[0]
        assert "name" not in jobs[0]
        assert "user_common_name" not in jobs[0]

    async def test_sem_filtro_traz_a_situacao_real_de_cada_job(self):
        # Antes a busca fixava status=pending, entao um agendamento concluido
        # hoje sumia do contexto e a EVA o descrevia como ainda pendente.
        capturado = {}

        def handler(request: httpx.Request) -> httpx.Response:
            capturado["status"] = request.url.params.get("status")
            return httpx.Response(200, json={"data": []})

        monta_cliente(handler)
        await backend_client.fetch_jobs("tok")

        assert capturado["status"] is None

    async def test_repassa_status_e_data_quando_pedidos(self):
        capturado = {}

        def handler(request: httpx.Request) -> httpx.Response:
            capturado["status"] = request.url.params.get("status")
            capturado["date_set"] = request.url.params.get("date_set")
            return httpx.Response(200, json={"data": []})

        monta_cliente(handler)
        await backend_client.fetch_jobs("tok", status="pending", date_set="2026-09-13")

        assert capturado["status"] == "pending"
        assert capturado["date_set"] == "2026-09-13"

    async def test_resposta_sem_data_devolve_lista_vazia(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"erro": "formato inesperado"})

        monta_cliente(handler)
        assert await backend_client.fetch_jobs("tok") == []


class TestRoutes:
    async def test_filtra_pelo_motorista_e_descarta_texto_livre(self):
        capturado = {}

        def handler(request: httpx.Request) -> httpx.Response:
            capturado["id_driver"] = request.url.params.get("id_driver")
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id_route": "route-1",
                            "name": "Coletas zona sul",
                            "status": "in_progress",
                            "city": "Sao Paulo",
                            "date_start": "2026-09-11T08:00:00Z",
                            "description": "texto livre do adm",
                            "user_feedback": "relato do motorista",
                            "id_driver": "driver-1",
                        }
                    ]
                },
            )

        monta_cliente(handler)
        rotas = await backend_client.fetch_routes("tok", "driver-1")

        assert capturado["id_driver"] == "driver-1"
        assert rotas[0]["name"] == "Coletas zona sul"
        assert "description" not in rotas[0]
        assert "user_feedback" not in rotas[0]

    async def test_paradas_descartam_descricao_e_limpam_o_endereco(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id_route": "route-1",
                    "stops": [
                        {
                            "id_route_donation_step": "stop-1",
                            "stop_order": 1,
                            "status": "pending",
                            "description": "doadora com intercorrencia",
                            "address": {
                                "street": "Rua Loefgren",
                                "number": "101",
                                "city": "Sao Paulo",
                                "zipcode": "04040-000",
                                "id_user": "usuario-secreto",
                                "created_by": "alguem",
                            },
                        }
                    ],
                },
            )

        monta_cliente(handler)
        paradas = await backend_client.fetch_route_stops("tok", "route-1")

        assert paradas[0]["stop_order"] == 1
        assert "description" not in paradas[0]
        assert paradas[0]["address"]["street"] == "Rua Loefgren"
        assert "id_user" not in paradas[0]["address"]
        assert "created_by" not in paradas[0]["address"]

    async def test_erro_de_rede_devolve_lista_vazia(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("estourou")

        monta_cliente(handler)
        assert await backend_client.fetch_routes("tok", "driver-1") == []
        assert await backend_client.fetch_route_stops("tok", "route-1") == []
