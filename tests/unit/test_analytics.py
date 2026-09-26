import zlib
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics import consultas
from app.services.analytics.periodo import resolver_periodo
from tests.conftest import insert_bottle, insert_donation_step

TUDO = resolver_periodo("tudo")


def _agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _usuario(
    db: AsyncSession,
    id_user: str,
    tipo: str,
    nome: str,
    exame_ate: datetime | None = None,
    cidade: str | None = None,
    bairro: str | None = None,
) -> None:
    agora = _agora()
    await db.execute(
        text(
            'INSERT INTO "user" (id_user, type, name, cpf, birth_date, phone_number, '
            "email, password, created_at, created_by, blood_exam_valid_until) VALUES "
            "(:id, :tipo, :nome, :cpf, :nasc, :tel, :email, 'segredo', :agora, :id, :exame)"
        ),
        {
            "id": id_user,
            "tipo": tipo,
            "nome": nome,
            "cpf": f"{zlib.crc32(id_user.encode()) % 10**11:011d}",
            "nasc": agora - timedelta(days=365 * 30),
            "tel": f"119{zlib.crc32(nome.encode()) % 10**8:08d}",
            "email": f"{id_user}@teste.com",
            "agora": agora - timedelta(days=60),
            "exame": exame_ate,
        },
    )
    if cidade:
        await db.execute(
            text(
                "INSERT INTO address (id_address, id_user, zipcode, street, city, state, "
                "neighborhood, created_at) VALUES "
                "(:id, :user, '00000000', 'Rua Teste', :cidade, 'SP', :bairro, :agora)"
            ),
            {"id": f"end_{id_user}", "user": id_user, "cidade": cidade, "bairro": bairro, "agora": agora},
        )


async def _doacao(
    db: AsyncSession,
    id_donation: str,
    doadora: str,
    ativa: bool,
    criada: datetime,
    recorrente: bool = False,
    nota: int | None = None,
) -> None:
    await db.execute(
        text(
            "INSERT INTO donation (id_donation, created_by, is_active, is_recurrent, "
            "score_feedback, created_at) VALUES (:id, :user, :ativa, :rec, :nota, :criada)"
        ),
        {"id": id_donation, "user": doadora, "ativa": ativa, "rec": recorrente, "nota": nota, "criada": criada},
    )


async def _rota(
    db: AsyncSession,
    id_route: str,
    motorista: str,
    status: str,
    data: datetime,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    km: float | None = None,
) -> None:
    await db.execute(
        text(
            "INSERT INTO route (id_route, id_driver, name, status, date_set, date_start, "
            "date_end, mileage, estimated_time, created_at, created_by) VALUES "
            "(:id, :motorista, :nome, :status, :data, :inicio, :fim, :km, :estimado, :data, 'adm')"
        ),
        {
            "id": id_route,
            "motorista": motorista,
            "nome": f"Rota {id_route}",
            "status": status,
            "data": data,
            "inicio": inicio,
            "fim": fim,
            "km": km,
            "estimado": int(4 * 3.6e12),
        },
    )


async def _parada(db: AsyncSession, id_parada: str, rota: str, etapa: str, status: str) -> None:
    await db.execute(
        text(
            "INSERT INTO route_donation_step (id_route_donation_step, id_route, "
            "id_donation_step, stop_order, status, created_at, created_by) VALUES "
            "(:id, :rota, :etapa, 1, :status, :agora, 'adm')"
        ),
        {"id": id_parada, "rota": rota, "etapa": etapa, "status": status, "agora": _agora()},
    )


async def _agendamento(
    db: AsyncSession, id_job: str, enfermeira: str, etapa: str, status: str, data: datetime
) -> None:
    await db.execute(
        text(
            "INSERT INTO job (id_job, id_user, id_step, status, name, description, date_set, "
            "created_at, created_by) VALUES "
            "(:id, :enf, :etapa, :status, 'Coleta domiciliar', 'texto clinico livre', :data, :data, 'adm')"
        ),
        {"id": id_job, "enf": enfermeira, "etapa": etapa, "status": status, "data": data},
    )


@pytest_asyncio.fixture(loop_scope="session")
async def cenario(db_session: AsyncSession) -> AsyncSession:
    agora = _agora()
    db = db_session

    await _usuario(db, "mot_carlos", "driver", "Carlos Motorista")
    await _usuario(db, "mot_marta", "driver", "Marta Motorista")
    await _usuario(db, "enf_ana", "nurse", "Ana Enfermeira")
    await _usuario(db, "doa_bia", "common", "Beatriz Souza", agora + timedelta(days=10), "Sao Paulo", "Pinheiros")
    await _usuario(db, "doa_cami", "common", "Camila Rocha", None, "Sao Paulo", "Moema")
    await _usuario(db, "doa_dani", "common", "Daniela Lima", agora - timedelta(days=5), "Osasco", "Centro")

    await _doacao(db, "don_bia", "doa_bia", True, agora - timedelta(days=5), recorrente=True)
    await _doacao(db, "don_cami", "doa_cami", True, agora - timedelta(days=3))
    await _doacao(db, "don_dani", "doa_dani", False, agora - timedelta(days=20), nota=5)
    await db.commit()

    await insert_donation_step(db, "st_bia_exame", "don_bia", "Exame de sangue", "done", agora - timedelta(days=5))
    await insert_donation_step(db, "st_bia_kit", "don_bia", "Entregar kit de ordenha", "done", agora - timedelta(days=4))
    await insert_donation_step(
        db, "st_bia_coleta", "don_bia", "Coletar leite", "pending", agora - timedelta(days=3),
        set_date=agora - timedelta(days=10),
    )
    await insert_donation_step(db, "st_cami_exame", "don_cami", "Exame de sangue", "failed", agora - timedelta(days=3))
    await insert_donation_step(db, "st_dani_coleta", "don_dani", "Coletar leite", "done", agora - timedelta(days=19))
    await insert_donation_step(db, "st_dani_analise", "don_dani", "Análise de leite", "done", agora - timedelta(days=18))

    await insert_bottle(db, "fr_bia_1", "don_bia", "250.00")
    await insert_bottle(db, "fr_bia_2", "don_bia", "250.00")
    await insert_bottle(db, "fr_bia_3", "don_bia", "200.00", discarded=True)
    await insert_bottle(db, "fr_dani_1", "don_dani", "300.00")
    await insert_bottle(db, "fr_dani_2", "don_dani", "300.00")
    await insert_bottle(db, "fr_dani_3", "don_dani", "200.00")

    dois_dias = agora - timedelta(days=2)
    await _rota(db, "r1", "mot_carlos", "done", dois_dias, dois_dias, dois_dias + timedelta(hours=5), 40)
    um_dia = agora - timedelta(days=1)
    await _rota(db, "r2", "mot_marta", "done", um_dia, um_dia, um_dia + timedelta(hours=7), 60)
    await _rota(db, "r3", "mot_carlos", "in_progress", agora, agora - timedelta(hours=5, minutes=30))
    await _parada(db, "p1", "r1", "st_dani_coleta", "done")
    await _parada(db, "p2", "r1", "st_bia_kit", "done")
    await _parada(db, "p3", "r2", "st_cami_exame", "error")
    await _parada(db, "p4", "r3", "st_bia_coleta", "pending")

    await _agendamento(db, "j1", "enf_ana", "st_bia_exame", "done", agora - timedelta(days=4))
    await _agendamento(db, "j2", "enf_ana", "st_cami_exame", "failed", agora - timedelta(days=2))
    await _agendamento(db, "j3", "enf_ana", "st_bia_coleta", "pending", agora - timedelta(days=1))
    await db.commit()
    return db


async def test_visao_geral_soma_frascos_nao_descartados(cenario: AsyncSession):
    dados = await consultas.visao_geral(cenario, TUDO)

    assert dados["litros_coletados"] == 1.3
    assert dados["frascos"] == 6
    assert dados["frascos_descartados"] == 1
    assert dados["taxa_de_descarte_pct"] == 16.7
    assert dados["doacoes_no_periodo"] == 3
    assert dados["doacoes_recorrentes"] == 1
    assert dados["doadoras_com_doacao_ativa_agora"] == 2
    assert dados["satisfacao_media_1_a_5"] == 5.0


async def test_periodo_recorta_pela_data_da_doacao(cenario: AsyncSession):
    semana = resolver_periodo("ultimos_7_dias")

    dados = await consultas.visao_geral(cenario, semana)

    assert dados["doacoes_no_periodo"] == 2
    assert dados["litros_coletados"] == 0.5


async def test_cadeia_fria_mede_as_6_horas(cenario: AsyncSession):
    dados = await consultas.cadeia_fria(cenario, TUDO)

    assert dados["rotas_no_periodo"] == 3
    assert dados["rotas_com_duracao_medida"] == 2
    assert dados["rotas_dentro_de_6h"] == 1
    assert dados["rotas_acima_de_6h"] == 1
    assert dados["conformidade_6h_pct"] == 50.0
    assert dados["duracao_media_horas"] == 6.0
    assert [r["rota"] for r in dados["rotas_que_passaram_de_6h"]] == ["Rota r2"]

    andamento = dados["rotas_em_andamento_agora"]
    assert len(andamento) == 1
    assert andamento[0]["motorista"] == "Carlos Motorista"
    assert andamento[0]["em_alerta"] is True
    assert andamento[0]["passou_de_6h"] is False
    assert andamento[0]["horas_restantes_ate_6h"] == pytest.approx(0.5, abs=0.1)


async def test_logistica_calcula_km_por_litro(cenario: AsyncSession):
    dados = await consultas.logistica(cenario, TUDO)

    assert dados["rotas_concluidas"] == 2
    assert dados["km_rodados"] == 100.0
    assert dados["litros_coletados_nas_rotas"] == 1.3
    assert dados["km_por_litro_coletado"] == pytest.approx(76.92, abs=0.01)
    assert dados["paradas_com_imprevisto"] == 1
    assert dados["taxa_de_imprevisto_pct"] == 25.0


async def test_funil_aponta_etapas_e_fila(cenario: AsyncSession):
    dados = await consultas.funil_doadora(cenario, TUDO)

    etapas = {e["etapa"]: e for e in dados["etapas"]}
    assert [e["etapa"] for e in dados["etapas"]] == list(consultas.ETAPAS)
    assert etapas["Exame de sangue"]["doacoes_que_chegaram"] == 2
    assert etapas["Exame de sangue"]["doacoes_que_concluiram"] == 1
    assert etapas["Coletar leite"]["doacoes_ativas_nesta_etapa_agora"] == 1
    assert etapas["Coletar leite"]["paradas_ha_mais_de_7_dias"] == 1


async def test_desempenho_por_motorista_e_enfermeira(cenario: AsyncSession):
    motoristas = {m["motorista"]: m for m in (await consultas.desempenho_motoristas(cenario, TUDO))["motoristas"]}
    assert motoristas["Carlos Motorista"]["rotas"] == 2
    assert motoristas["Carlos Motorista"]["conformidade_6h_pct"] == 100.0
    assert motoristas["Marta Motorista"]["conformidade_6h_pct"] == 0.0
    assert motoristas["Marta Motorista"]["paradas_com_imprevisto"] == 1

    enfermagem = (await consultas.desempenho_enfermagem(cenario, TUDO))["enfermagem"]
    assert enfermagem == [
        {
            "enfermeira": "Ana Enfermeira",
            "agendamentos": 3,
            "concluidos": 1,
            "nao_realizados": 1,
            "pendentes": 1,
            "pendentes_com_data_ja_passada": 1,
            "taxa_de_conclusao_pct": 50.0,
        }
    ]


async def test_regioes_agrupam_pelo_endereco_da_doadora(cenario: AsyncSession):
    dados = await consultas.regioes(cenario, TUDO)

    regioes = {r["regiao"]: r for r in dados["regioes"]}
    assert regioes["Osasco"]["litros"] == 0.8
    assert regioes["Sao Paulo"]["doadoras"] == 2
    assert dados["regioes"][0]["regiao"] == "Osasco"


async def test_alertas_operacionais(cenario: AsyncSession):
    dados = await consultas.alertas(cenario)

    assert dados["total_de_rotas_em_andamento_agora"] == 1
    assert [e["doadora"] for e in dados["exames_vencendo_em_30_dias"]] == ["Beatriz Souza"]
    assert dados["exames_vencidos_com_doacao_ativa"] == []
    assert len(dados["rotas_em_alerta_5h"]) == 1
    assert dados["agendamentos_atrasados"] == 1
    assert [d["doadora"] for d in dados["doacoes_paradas_ha_mais_de_7_dias"]] == ["Beatriz Souza"]


async def test_lista_de_doadoras_nao_expoe_dado_sensivel(cenario: AsyncSession):
    dados = await consultas.listar_doadoras(cenario)

    doadoras = {d["doadora"]: d for d in dados["doadoras"]}
    assert set(doadoras) == {"Beatriz Souza", "Camila Rocha"}

    camila = doadoras["Camila Rocha"]
    assert camila["situacao_da_etapa"] == "aguardando retorno da equipe"
    assert camila["cpf"].startswith("***.")
    assert camila["telefone"].startswith("(**) *****-")

    for doadora in dados["doadoras"]:
        assert "email" not in doadora
        assert "password" not in doadora
        texto = str(doadora)
        assert "reprovad" not in texto
        assert "@teste.com" not in texto
        assert "segredo" not in texto


async def test_lista_filtra_exame_vencendo(cenario: AsyncSession):
    dados = await consultas.listar_doadoras(cenario, exame="vencendo")

    assert [d["doadora"] for d in dados["doadoras"]] == ["Beatriz Souza"]


async def test_lista_de_agendamentos_nao_traz_texto_livre(cenario: AsyncSession):
    dados = await consultas.listar_agendamentos(cenario, TUDO)

    assert dados["total_listado"] == 3
    for agendamento in dados["agendamentos"]:
        assert "texto clinico" not in str(agendamento)
        assert "Coleta domiciliar" not in str(agendamento)


async def test_lista_de_rotas_traduz_a_situacao(cenario: AsyncSession):
    dados = await consultas.listar_rotas(cenario, TUDO, situacao="in_progress")

    assert [r["situacao"] for r in dados["rotas"]] == ["em andamento"]


async def test_operacao_agora_resume_o_dia(cenario: AsyncSession):
    dados = await consultas.operacao_agora(cenario)

    assert len(dados["rotas_em_andamento"]) == 1
    assert dados["alertas"]["exames_vencendo_em_30_dias"] == 1
    assert dados["alertas"]["rotas_em_alerta_5h"] == 1


def test_periodo_personalizado_inverte_datas_trocadas():
    periodo = resolver_periodo(inicio=date(2026, 9, 30), fim=date(2026, 9, 1))

    assert periodo.inicio == date(2026, 9, 1)
    assert periodo.fim == date(2026, 9, 30)


def test_mes_anterior_atravessa_o_ano():
    periodo = resolver_periodo("mes_anterior", hoje=date(2026, 1, 15))

    assert periodo.inicio == date(2025, 12, 1)
    assert periodo.fim == date(2025, 12, 31)


def test_limites_do_periodo_em_utc():
    periodo = resolver_periodo("hoje", hoje=date(2026, 9, 26))

    assert periodo.inicio_utc == datetime(2026, 9, 26, 3, 0)
    assert periodo.fim_utc == datetime(2026, 9, 27, 3, 0)
