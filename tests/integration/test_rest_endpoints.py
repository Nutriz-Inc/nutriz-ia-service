# Testes de integracao dos endpoints REST (httpx.AsyncClient + ASGITransport).

import httpx

from tests.conftest import make_token


def _client(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_health(app_with_overrides):
    async with _client(app_with_overrides) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "nutriz-ia-service"}


async def test_me_retorna_user_id(app_with_overrides, valid_token, seed_user):
    async with _client(app_with_overrides) as client:
        response = await client.get("/me", headers=_auth(valid_token))
    assert response.status_code == 200
    assert response.json() == {"user_id": seed_user}


async def test_me_sem_token_retorna_401(app_with_overrides, seed_user):
    async with _client(app_with_overrides) as client:
        response = await client.get("/me")
    assert response.status_code == 401


async def test_me_profile_completo(app_with_overrides, valid_token, seed_baby_and_address, seed_consent):
    async with _client(app_with_overrides) as client:
        response = await client.get("/me/profile", headers=_auth(valid_token))
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["name"] == "Usuaria Teste"
    assert body["profile"]["baby"]["name"] == "Joao"
    assert body["profile"]["address"]["neighborhood"] == "Vila Mariana"
    assert body["consent"]["has_valid_consent"] is True
    assert body["consent"]["terms_version"] == "v1.0"


async def test_me_profile_usuario_inexistente_404(app_with_overrides, test_engine):
    token = make_token(user_id="00000000-0000-0000-0000-000000000000")
    async with _client(app_with_overrides) as client:
        response = await client.get("/me/profile", headers=_auth(token))
    assert response.status_code == 404


async def test_listagem_de_conversas_vazia(app_with_overrides, valid_token, seed_user):
    async with _client(app_with_overrides) as client:
        response = await client.get("/conversations", headers=_auth(valid_token))
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_listagem_de_conversas_e_mensagens(
    app_with_overrides, valid_token, seed_user, db_session
):
    from app.services import chat_service

    conversation = await chat_service.get_or_create_conversation(db_session, seed_user, None)
    await chat_service.save_message(db_session, conversation.id, "user", "oi")
    await chat_service.save_message(db_session, conversation.id, "assistant", "ola!")

    async with _client(app_with_overrides) as client:
        conversas = await client.get("/conversations", headers=_auth(valid_token))
        mensagens = await client.get(
            f"/conversations/{conversation.id}/messages", headers=_auth(valid_token)
        )

    assert conversas.status_code == 200
    assert conversas.json()["total"] == 1

    assert mensagens.status_code == 200
    roles = [m["role"] for m in mensagens.json()]
    assert roles == ["user", "assistant"]


async def test_mensagens_de_conversa_de_outro_usuario_403(
    app_with_overrides, seed_user, db_session
):
    from app.services import chat_service

    conversation = await chat_service.get_or_create_conversation(db_session, seed_user, None)
    token_de_outra = make_token(user_id="99999999-9999-9999-9999-999999999999")

    async with _client(app_with_overrides) as client:
        response = await client.get(
            f"/conversations/{conversation.id}/messages", headers=_auth(token_de_outra)
        )
    assert response.status_code == 403


async def test_mensagens_de_conversa_inexistente_404(
    app_with_overrides, valid_token, seed_user
):
    async with _client(app_with_overrides) as client:
        response = await client.get(
            "/conversations/00000000-0000-0000-0000-000000000000/messages",
            headers=_auth(valid_token),
        )
    assert response.status_code == 404
