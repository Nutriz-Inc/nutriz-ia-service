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


def _collect_turn_with_action(ws):
    """Le o turno ate 'done' e retorna (texto, frame_de_acao_ou_None)."""
    response = ""
    action = None
    while True:
        event = ws.receive_json()
        etype = event["type"]
        if etype == "chunk":
            response += event["content"]
        elif etype == "action":
            action = event
        elif etype == "done":
            return response, action
        elif etype == "error":
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


class TestStaffBloqueado:
    # Staff (adm/nurse) nao usa a EVA: o backend recusa a conexao mesmo com
    # token valido - o gate de UI no front nao e suficiente sozinho.
    STAFF_IDS = {
        "adm": "44444444-4444-4444-4444-444444444444",
        "nurse": "55555555-5555-5555-5555-555555555555",
    }

    async def _seed_staff(self, db_session, user_type: str) -> str:
        from datetime import datetime, timezone

        staff_id = self.STAFF_IDS[user_type]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        await db_session.execute(
            text(
                'INSERT INTO "user" (id_user, type, name, cpf, birth_date, '
                "phone_number, email, password, created_at, created_by) VALUES "
                "(:id, :type, 'Staff Teste', :cpf, :birth, :phone, :email, "
                "'hash', :now, :id)"
            ),
            {
                "id": staff_id,
                "type": user_type,
                "cpf": f"9999999990{1 if user_type == 'adm' else 2}",
                "birth": now,
                "phone": f"1198888000{1 if user_type == 'adm' else 2}",
                "email": f"{user_type}@nutriz.com",
                "now": now,
            },
        )
        await db_session.commit()
        return staff_id

    @pytest.mark.parametrize("user_type", ["adm", "nurse"])
    async def test_staff_recebe_erro_e_fecha_4403(
        self, app_with_overrides, db_session, user_type
    ):
        staff_id = await self._seed_staff(db_session, user_type)
        token = make_token(user_id=staff_id)
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={token}") as ws:
                event = ws.receive_json()
                assert event["type"] == "error"
                assert event["code"] == "staff_not_allowed"
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_json()
                assert exc.value.code == 4403

        count = await db_session.execute(text("SELECT count(*) FROM conversations"))
        assert count.scalar_one() == 0

    def test_nutriz_common_segue_permitida(
        self, app_with_overrides, seed_consent, valid_token
    ):
        # Garante que o bloqueio de staff nao afeta o papel common
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                event = ws.receive_json()
                assert event["type"] == "conversation"


class TestFrameDeAcaoAutenticado:
    def test_whatsapp_emite_frame(
        self, app_with_overrides, seed_consent, valid_token, fake_provider: FakeProvider
    ):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                ws.send_json({"message": "queria falar com alguem da equipe"})
                _, action = _collect_turn_with_action(ws)

        assert action is not None
        assert action["action"] == "whatsapp"
        assert action["label"] == "Falar no WhatsApp"

    def test_signup_nao_dispara_para_nutriz_logada(
        self, app_with_overrides, seed_consent, valid_token, fake_provider: FakeProvider
    ):
        # Mesma frase de signup, mas na conexao autenticada nao pode emitir
        # signup - e nenhuma outra regra casa, entao nao ha frame de acao.
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                ws.send_json({"message": "Como faço para me cadastrar?"})
                _, action = _collect_turn_with_action(ws)

        assert action is None

    def test_pergunta_generica_nao_emite_frame(
        self, app_with_overrides, seed_consent, valid_token, fake_provider: FakeProvider
    ):
        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                ws.send_json({"message": "qual a temperatura ideal do leite?"})
                _, action = _collect_turn_with_action(ws)

        assert action is None


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


class TestRagNoFluxoDoChat:
    """Regressao do bug do RAG: chunk relevante DEVE entrar no prompt do LLM."""

    async def _ingerir_chunk(self, db_session, content: str, source: str) -> None:
        from tests.conftest import fake_encode
        from app.models import KbChunk

        db_session.add(
            KbChunk(source=source, content=content, embedding=fake_encode(content))
        )
        await db_session.commit()

    async def test_chunk_relevante_sempre_entra_no_prompt(
        self, app_with_overrides, seed_consent, valid_token, fake_provider, db_session
    ):
        # Anti-bypass: havendo documento correspondente, o trecho tem que
        # chegar ao LLM. Se o RAG for contornado, o prompt nao o conteria.
        conteudo = "ordenha manual do leite humano com maos higienizadas"
        await self._ingerir_chunk(db_session, conteudo, "ordenha_leite_humano")

        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                ws.send_json({"message": "ordenha manual do leite humano higienizadas"})
                _collect_turn(ws)

        system_prompt = fake_provider.calls[-1][0]["content"]
        assert "CONTEXTO DOS PROTOCOLOS" in system_prompt
        assert conteudo in system_prompt

    async def test_sem_documento_correspondente_prompt_sem_contexto(
        self, app_with_overrides, seed_consent, valid_token, fake_provider, db_session
    ):
        # Sem chunk relevante: EVA cai no modo conhecimento geral, sem secao
        # de contexto e sem dizer "nao sei".
        await self._ingerir_chunk(
            db_session, "texto totalmente sem relacao xyz abcdef", "outro"
        )

        with TestClient(app_with_overrides) as client:
            with client.websocket_connect(f"/ws/chat?token={valid_token}") as ws:
                ws.receive_json()
                ws.send_json({"message": "ordenha manual leite humano doacao"})
                _collect_turn(ws)

        system_prompt = fake_provider.calls[-1][0]["content"]
        assert "CONTEXTO DOS PROTOCOLOS" not in system_prompt
        assert "conhecimento geral confiavel" in system_prompt
