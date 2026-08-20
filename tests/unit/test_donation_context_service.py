# Testes do contexto de doacao da nutriz (donation + donation_step + address).
#
# Alem do comportamento, esta suite guarda o LIMITE INVIOLAVEL da missao:
# nenhum dado clinico pode sair deste servico rumo ao prompt da Groq.

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import donation_context_service
from app.services.donation_context_service import (
    _next_step_name,
    _status_label,
    get_donation_context,
)
from tests.conftest import (
    SEED_DONATION_ACTIVE_ID,
    SEED_DONATION_POINT_NAME,
    SEED_USER_ID,
    insert_donation_step,
)


def _naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Etapa atual, agendamento e local
# ---------------------------------------------------------------------------

async def test_doacao_em_andamento_traz_etapa_atual_e_proxima(
    db_session: AsyncSession, seed_donations: str
):
    context = await get_donation_context(db_session, seed_donations)

    assert context.donation is not None
    assert context.donation.id_donation == SEED_DONATION_ACTIVE_ID
    assert context.donation.is_active is True
    # Exame e kit estao 'done'; a primeira etapa nao concluida e a coleta.
    assert context.donation.current_step_name == "Coletar leite"
    assert context.donation.current_step_status_label == "pendente"
    assert context.donation.next_step_name == "Análise de leite"


async def test_data_prevista_da_etapa_atual_vem_do_set_date(
    db_session: AsyncSession, seed_donations: str
):
    context = await get_donation_context(db_session, seed_donations)

    assert context.donation is not None
    prevista = context.donation.current_step_set_date
    assert prevista is not None
    assert (prevista - _naive_now()).days in (4, 5)


async def test_local_de_coleta_vem_do_ponto_de_coleta_da_etapa(
    db_session: AsyncSession, seed_donations: str
):
    context = await get_donation_context(db_session, seed_donations)

    assert context.donation is not None
    assert context.donation.place is not None
    assert context.donation.place.donation_point_name == SEED_DONATION_POINT_NAME
    assert context.donation.place.neighborhood == "Vila Clementino"
    assert context.donation.place.city == "Sao Paulo"
    assert context.donation.place.state == "SP"


async def test_etapa_sem_endereco_herda_o_local_da_ultima_etapa_que_teve(
    db_session: AsyncSession, seed_donations: str
):
    # A coleta (com endereco) e concluida e a analise, sem endereco, vira a
    # etapa atual: a nutriz continua sabendo onde esteve por ultimo.
    now = _naive_now()
    await db_session.execute(
        text(
            "UPDATE donation_step SET status = 'done' "
            "WHERE id_donation_step = 'dst_coleta'"
        )
    )
    await db_session.commit()
    await insert_donation_step(
        db_session,
        "dst_analise",
        SEED_DONATION_ACTIVE_ID,
        "Análise de leite",
        "pending",
        now,
    )

    context = await get_donation_context(db_session, seed_donations)

    assert context.donation is not None
    assert context.donation.current_step_name == "Análise de leite"
    assert context.donation.next_step_name is None
    assert context.donation.place is not None
    assert context.donation.place.donation_point_name == SEED_DONATION_POINT_NAME


async def test_todas_as_etapas_concluidas_zera_a_etapa_atual(
    db_session: AsyncSession, seed_donations: str
):
    now = _naive_now()
    await db_session.execute(
        text("UPDATE donation_step SET status = 'done' WHERE id_donation = :id"),
        {"id": SEED_DONATION_ACTIVE_ID},
    )
    await db_session.commit()
    await insert_donation_step(
        db_session,
        "dst_analise",
        SEED_DONATION_ACTIVE_ID,
        "Análise de leite",
        "done",
        now,
    )

    context = await get_donation_context(db_session, seed_donations)

    assert context.donation is not None
    assert context.donation.current_step_name is None
    assert context.donation.current_step_status_label is None
    assert context.donation.next_step_name is None


async def test_etapa_ainda_nao_aberta_pela_equipe_fica_sem_status(
    db_session: AsyncSession, seed_user: str
):
    # Doacao criada, nenhuma etapa registrada ainda pela equipe Lactare.
    await db_session.execute(
        text(
            "INSERT INTO donation (id_donation, created_by, is_active, created_at) "
            "VALUES ('don_semstep', :user, true, :now)"
        ),
        {"user": seed_user, "now": _naive_now()},
    )
    await db_session.commit()

    context = await get_donation_context(db_session, seed_user)

    assert context.donation is not None
    assert context.donation.current_step_name == "Exame de sangue"
    assert context.donation.current_step_status_label is None


# ---------------------------------------------------------------------------
# LIMITE INVIOLAVEL: nada de clinico sai daqui
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["warn", "failed"])
async def test_status_negativo_do_exame_de_sangue_e_mascarado(
    db_session: AsyncSession, seed_donations: str, status: str
):
    # O status da etapa "Exame de sangue" revela por inferencia o resultado da
    # sorologia. Nao pode chegar cru ao prompt: vira um rotulo neutro.
    await db_session.execute(
        text(
            "UPDATE donation_step SET status = :status "
            "WHERE id_donation_step = 'dst_exame'"
        ),
        {"status": status},
    )
    await db_session.commit()

    context = await get_donation_context(db_session, seed_donations)

    assert context.donation is not None
    assert context.donation.current_step_name == "Exame de sangue"
    assert (
        context.donation.current_step_status_label
        == "aguardando retorno da equipe Lactare"
    )


def test_mascara_so_vale_para_a_etapa_clinica():
    assert (
        _status_label("Exame de sangue", "failed")
        == "aguardando retorno da equipe Lactare"
    )
    assert _status_label("Exame de sangue", "done") == "concluida"
    assert _status_label("Coletar leite", "failed") == "nao aprovada"
    assert _status_label("Coletar leite", None) is None


async def test_descricao_clinica_da_etapa_nunca_entra_no_contexto(
    db_session: AsyncSession, seed_donations: str
):
    # donation_step.description e texto livre de adm ("sorologia reagente",
    # motivo de inaptidao). A coluna nem e mapeada no ORM - este teste garante
    # que ela continue fora do objeto entregue ao prompt.
    context = await get_donation_context(db_session, seed_donations)

    assert context.donation is not None
    serializado = context.model_dump_json().lower()
    for proibido in ("description", "descricao", "user_feedback", "sorologia"):
        assert proibido not in serializado


def test_ordem_canonica_das_etapas_bate_com_o_enum_do_go():
    assert donation_context_service.STEP_ORDER == (
        "Exame de sangue",
        "Entregar kit de ordenha",
        "Coletar leite",
        "Análise de leite",
    )
    assert _next_step_name("Exame de sangue") == "Entregar kit de ordenha"
    assert _next_step_name("Análise de leite") is None
    assert _next_step_name(None) is None
    assert _next_step_name("etapa que nao existe") is None


# ---------------------------------------------------------------------------
# Historico
# ---------------------------------------------------------------------------

async def test_historico_soma_volume_e_conta_doacoes(
    db_session: AsyncSession, seed_donations: str
):
    context = await get_donation_context(db_session, seed_donations)

    assert context.history is not None
    assert context.history.total_donations == 2
    assert context.history.concluded_donations == 1
    assert context.history.total_volume_ml == Decimal("1250.00")
    assert context.history.last_donation_at is not None


async def test_nutriz_sem_doacoes_nao_e_erro(db_session: AsyncSession, seed_user: str):
    context = await get_donation_context(db_session, seed_user)

    assert context.donation is None
    assert context.history is not None
    assert context.history.total_donations == 0
    assert context.history.total_volume_ml is None
    assert context.history.last_donation_at is None
    # is_empty() e sobre falha de leitura, nao sobre ausencia de doacoes.
    assert context.is_empty() is False


async def test_doacao_de_outra_nutriz_nao_vaza(
    db_session: AsyncSession, seed_donations: str
):
    now = _naive_now()
    await db_session.execute(
        text(
            'INSERT INTO "user" (id_user, type, name, cpf, birth_date, '
            "phone_number, email, password, created_at, created_by) VALUES "
            "('outra-nutriz', 'common', 'Outra', '99999999999', :birth, "
            "'11888880000', 'outra@nutriz.com', 'hash', :now, 'outra-nutriz')"
        ),
        {"birth": now - timedelta(days=365 * 30), "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO donation (id_donation, created_by, is_active, "
            "quantity_donated, created_at) VALUES "
            "('don_outra', 'outra-nutriz', true, 9999.00, :now)"
        ),
        {"now": now},
    )
    await db_session.commit()

    context = await get_donation_context(db_session, seed_donations)

    assert context.history is not None
    assert context.history.total_donations == 2
    assert context.history.total_volume_ml == Decimal("1250.00")
    assert context.donation is not None
    assert context.donation.id_donation != "don_outra"


async def test_doacao_removida_e_ignorada(
    db_session: AsyncSession, seed_donations: str
):
    await db_session.execute(
        text("UPDATE donation SET removed_at = :now WHERE id_donation = :id"),
        {"now": _naive_now(), "id": SEED_DONATION_ACTIVE_ID},
    )
    await db_session.commit()

    context = await get_donation_context(db_session, seed_donations)

    assert context.history is not None
    assert context.history.total_donations == 1
    assert context.history.total_volume_ml == Decimal("700.00")
    # Sem doacao ativa, cai na mais recente que sobrou (a ja encerrada).
    assert context.donation is not None
    assert context.donation.is_active is False


# ---------------------------------------------------------------------------
# Resiliencia: falha degrada o bloco, nunca derruba o chat
# ---------------------------------------------------------------------------

async def test_falha_total_na_leitura_degrada_sem_propagar():
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = Exception('relation "donation" does not exist')

    context = await get_donation_context(db, SEED_USER_ID)

    assert context.donation is None
    assert context.history is None
    assert context.is_empty() is True
    # Rollback por bloco: sem ele a sessao ficaria em transacao abortada e o
    # resto do turno (historico de mensagens, RAG, persistencia) falharia junto.
    assert db.rollback.await_count == 2


async def test_falha_na_doacao_atual_nao_impede_o_historico(
    db_session: AsyncSession, seed_donations: str, monkeypatch: pytest.MonkeyPatch
):
    async def explode(db, id_user):
        raise Exception("falha simulada na leitura da doacao atual")

    monkeypatch.setattr(donation_context_service, "_load_current_donation", explode)

    context = await get_donation_context(db_session, seed_donations)

    assert context.donation is None
    assert context.history is not None
    assert context.history.total_donations == 2


async def test_falha_no_historico_nao_impede_a_doacao_atual(
    db_session: AsyncSession, seed_donations: str, monkeypatch: pytest.MonkeyPatch
):
    async def explode(db, id_user):
        raise Exception("falha simulada na leitura do historico")

    monkeypatch.setattr(donation_context_service, "_load_history", explode)

    context = await get_donation_context(db_session, seed_donations)

    assert context.history is None
    assert context.donation is not None
    assert context.donation.current_step_name == "Coletar leite"
