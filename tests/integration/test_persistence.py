# Testes de persistencia do turno de chat: conversation, message e llm_audit.

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.conftest import FakeProvider


async def _run_turns(app, token: str, mensagens: list[str]) -> str:
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token}") as ws:
            conv_event = ws.receive_json()
            for mensagem in mensagens:
                ws.send_json({"message": mensagem})
                while True:
                    event = ws.receive_json()
                    if event["type"] == "done":
                        break
    return conv_event["conversation_id"]


async def test_turno_grava_duas_mensagens_e_um_audit(
    app_with_overrides, seed_consent, valid_token, db_session, fake_provider: FakeProvider
):
    conversation_id = await _run_turns(app_with_overrides, valid_token, ["Como doar?"])

    messages = (
        await db_session.execute(
            text(
                "SELECT role, content FROM messages WHERE conversation_id = :cid "
                "ORDER BY created_at"
            ),
            {"cid": conversation_id},
        )
    ).all()
    assert [(m.role) for m in messages] == ["user", "assistant"]
    assert messages[0].content == "Como doar?"
    assert messages[1].content == "Ola, sou a EVA de teste."

    audits = (
        await db_session.execute(
            text(
                "SELECT llm_provider, llm_model, latency_ms, user_id FROM llm_audit "
                "WHERE conversation_id = :cid"
            ),
            {"cid": conversation_id},
        )
    ).all()
    assert len(audits) == 1
    assert audits[0].llm_provider == "fake"
    assert audits[0].llm_model == "fake-model"
    assert audits[0].latency_ms is not None and audits[0].latency_ms >= 0
    assert audits[0].user_id == seed_consent


async def test_multiplos_turnos_gravam_tudo(
    app_with_overrides, seed_consent, valid_token, db_session, fake_provider: FakeProvider
):
    conversation_id = await _run_turns(
        app_with_overrides, valid_token, ["primeira", "segunda", "terceira"]
    )

    total_messages = (
        await db_session.execute(
            text("SELECT count(*) FROM messages WHERE conversation_id = :cid"),
            {"cid": conversation_id},
        )
    ).scalar_one()
    assert total_messages == 6  # 3 turnos x (user + assistant)

    total_audits = (
        await db_session.execute(
            text("SELECT count(*) FROM llm_audit WHERE conversation_id = :cid"),
            {"cid": conversation_id},
        )
    ).scalar_one()
    assert total_audits == 3


async def test_turno_atualiza_last_message_at(
    app_with_overrides, seed_consent, valid_token, db_session, fake_provider: FakeProvider
):
    conversation_id = await _run_turns(app_with_overrides, valid_token, ["oi"])

    row = (
        await db_session.execute(
            text(
                "SELECT started_at, last_message_at FROM conversations WHERE id = :cid"
            ),
            {"cid": conversation_id},
        )
    ).one()
    assert row.last_message_at >= row.started_at


async def test_audit_registra_prompt_e_chunks(
    app_with_overrides, seed_consent, valid_token, db_session, fake_provider: FakeProvider
):
    conversation_id = await _run_turns(app_with_overrides, valid_token, ["pergunta"])

    row = (
        await db_session.execute(
            text(
                "SELECT prompt_full, chunks_used FROM llm_audit WHERE conversation_id = :cid"
            ),
            {"cid": conversation_id},
        )
    ).one()
    # prompt_full guarda a lista de mensagens enviadas ao LLM (JSONB)
    import json

    prompt = row.prompt_full if isinstance(row.prompt_full, list) else json.loads(row.prompt_full)
    assert prompt[0]["role"] == "system"
    assert prompt[-1] == {"role": "user", "content": "pergunta"}
