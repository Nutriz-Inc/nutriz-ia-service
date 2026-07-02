# Testes de integracao do fluxo completo do WebSocket /ws/chat.
# LLM mockado via FakeProvider; banco pgvector real (de teste).

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.testclient import WebSocketDisconnect

from tests.conftest import FakeProvider, make_token


def _collect_turn(ws) -> str:
    """Envia nada; le eventos ate 'done' e retorna a resposta completa."""
    response = ""
    while True:
        event = ws.receive_json()
        if event["type"] == "chunk":
            response += event["content"]
        elif event["type"] == "done":
            return response
        elif event["type"] == "error":
            raise AssertionError(f"erro inesperado: {event}")


class TestAuthLgpd:
    def test_token_valido_com_consent_aceita_e_envia_conversa(
        self, app_with_overrides, seed_consent, valid_token
    ):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                event = ws.receive_json()
                assert event["type"] == "conversation"
                assert event["conversation_id"]

    def test_sem_token_fecha_4001(self, app_with_overrides, seed_consent):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect("/ws/chat") as ws:
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_json()
                assert exc.value.code == 4001

    def test_token_expirado_fecha_4001(self, app_with_overrides, seed_consent):
        token = make_token(expires_in=timedelta(hours=-1))
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={token}") as ws:
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_json()
                assert exc.value.code == 4001

    def test_token_malformado_fecha_4001(self, app_with_overrides, seed_consent):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect("/ws/chat?token=lixo") as ws:
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_json()
                assert exc.value.code == 4001

    def test_assinatura_errada_fecha_4001(self, app_with_overrides, seed_consent):
        token = make_token(secret="segredo-errado")
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={token}") as ws:
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_json()
                assert exc.value.code == 4001

    async def test_sem_consent_fecha_4003_e_nada_persistido(
        self, app_with_overrides, seed_user, valid_token, db_session
    ):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                event = ws.receive_json()
                assert event["type"] == "error"
                assert event["code"] == "lgpd_consent_required"
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_json()
                assert exc.value.code == 4003

        count = await db_session.execute(text("SELECT count(*) FROM conversations"))
        assert count.scalar_one() == 0


class TestChatFlow:
    def test_mensagem_simples_recebe_chunks_e_done(
        self, app_with_overrides, seed_consent, valid_token, fake_provider: FakeProvider
    ):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                ws.send_json({"message": "Como doar leite?"})
                response = _collect_turn(ws)
                assert response == "Ola, sou a EVA de teste."
                assert len(fake_provider.calls) == 1

    def test_multiplos_turnos_na_mesma_conexao(
        self, app_with_overrides, seed_consent, valid_token, fake_provider: FakeProvider
    ):
        # Regressao: sessao/cliente em estado inconsistente derrubava o 2o turno
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                for turno in range(3):
                    ws.send_json({"message": f"pergunta numero {turno}"})
                    response = _collect_turn(ws)
                    assert response == "Ola, sou a EVA de teste."
                assert len(fake_provider.calls) == 3

    def test_historico_do_turno_anterior_vai_para_o_llm(
        self, app_with_overrides, seed_consent, valid_token, fake_provider: FakeProvider
    ):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                ws.send_json({"message": "primeira pergunta"})
                _collect_turn(ws)
                ws.send_json({"message": "segunda pergunta"})
                _collect_turn(ws)

        segunda_chamada = fake_provider.calls[1]
        contents = [m["content"] for m in segunda_chamada]
        assert "primeira pergunta" in contents
        assert "Ola, sou a EVA de teste." in contents
        assert contents[-1] == "segunda pergunta"

    def test_mensagem_vazia_nao_derruba_conexao(
        self, app_with_overrides, seed_consent, valid_token, fake_provider: FakeProvider
    ):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                ws.send_json({"message": ""})
                event = ws.receive_json()
                assert event["type"] == "error"
                # Conexao segue viva: proximo turno funciona
                ws.send_json({"message": "pergunta valida"})
                assert _collect_turn(ws) == "Ola, sou a EVA de teste."

    def test_json_invalido_nao_derruba_conexao(
        self, app_with_overrides, seed_consent, valid_token, fake_provider: FakeProvider
    ):
        # Regressao: JSON invalido derrubava a conexao inteira
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                ws.send_text("isto nao e json {{{")
                event = ws.receive_json()
                assert event["type"] == "error"
                ws.send_json({"message": "pergunta valida"})
                assert _collect_turn(ws) == "Ola, sou a EVA de teste."

    def test_payload_nao_objeto_nao_derruba_conexao(
        self, app_with_overrides, seed_consent, valid_token, fake_provider: FakeProvider
    ):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                ws.send_text('"uma string json valida"')
                event = ws.receive_json()
                assert event["type"] == "error"
                ws.send_json({"message": "pergunta valida"})
                assert _collect_turn(ws) == "Ola, sou a EVA de teste."

    def test_reconexao_com_conversation_id_retoma_conversa(
        self, app_with_overrides, seed_consent, valid_token, fake_provider: FakeProvider
    ):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                conv_id = ws.receive_json()["conversation_id"]
                ws.send_json({"message": "primeira sessao"})
                _collect_turn(ws)

            with client.websocket_connect(
                f"/ws/chat?token={valid_token}&conversation_id={conv_id}"
            ) as ws:
                event = ws.receive_json()
                assert event["conversation_id"] == conv_id
                ws.send_json({"message": "segunda sessao"})
                _collect_turn(ws)

        # O historico da primeira sessao foi enviado ao LLM na segunda
        contents = [m["content"] for m in fake_provider.calls[-1]]
        assert "primeira sessao" in contents

    def test_conversation_id_invalido_fecha_4002(
        self, app_with_overrides, seed_consent, valid_token
    ):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(
                f"/ws/chat?token={valid_token}&conversation_id=nao-e-uuid"
            ) as ws:
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_json()
                assert exc.value.code == 4002
