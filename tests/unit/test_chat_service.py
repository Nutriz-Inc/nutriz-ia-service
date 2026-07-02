# Testes do chat_service: criacao/recuperacao de conversas e regras de dono.

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import chat_service


async def test_cria_conversa_nova_sem_id(db_session: AsyncSession, seed_user: str):
    conversation = await chat_service.get_or_create_conversation(db_session, seed_user, None)
    assert conversation.id is not None
    assert conversation.user_id == seed_user


async def test_recupera_conversa_existente_pelo_id(db_session: AsyncSession, seed_user: str):
    created = await chat_service.get_or_create_conversation(db_session, seed_user, None)
    recovered = await chat_service.get_or_create_conversation(db_session, seed_user, created.id)
    assert recovered.id == created.id


async def test_conversa_inexistente_levanta_404(db_session: AsyncSession, seed_user: str):
    with pytest.raises(HTTPException) as exc:
        await chat_service.get_or_create_conversation(db_session, seed_user, uuid.uuid4())
    assert exc.value.status_code == 404


async def test_conversa_de_outro_usuario_levanta_403(db_session: AsyncSession, seed_user: str):
    created = await chat_service.get_or_create_conversation(db_session, seed_user, None)
    with pytest.raises(HTTPException) as exc:
        await chat_service.get_or_create_conversation(
            db_session, "99999999-9999-9999-9999-999999999999", created.id
        )
    assert exc.value.status_code == 403


async def test_historico_limita_e_ordena_cronologicamente(
    db_session: AsyncSession, seed_user: str
):
    conversation = await chat_service.get_or_create_conversation(db_session, seed_user, None)
    for i in range(12):
        role = "user" if i % 2 == 0 else "assistant"
        await chat_service.save_message(db_session, conversation.id, role, f"msg {i}")

    history = await chat_service.get_recent_messages(db_session, conversation.id, limit=10)
    assert len(history) == 10
    # As 10 mais recentes (msg 2..11), em ordem cronologica
    assert history[0].content == "msg 2"
    assert history[-1].content == "msg 11"


async def test_list_messages_do_dono_retorna_todas(db_session: AsyncSession, seed_user: str):
    conversation = await chat_service.get_or_create_conversation(db_session, seed_user, None)
    await chat_service.save_message(db_session, conversation.id, "user", "oi")
    await chat_service.save_message(db_session, conversation.id, "assistant", "ola")

    messages = await chat_service.list_messages(db_session, conversation.id, seed_user)
    assert [m.role for m in messages] == ["user", "assistant"]


async def test_list_messages_conversa_inexistente_404(db_session: AsyncSession, seed_user: str):
    with pytest.raises(HTTPException) as exc:
        await chat_service.list_messages(db_session, uuid.uuid4(), seed_user)
    assert exc.value.status_code == 404


async def test_list_messages_de_outro_usuario_403(db_session: AsyncSession, seed_user: str):
    conversation = await chat_service.get_or_create_conversation(db_session, seed_user, None)
    with pytest.raises(HTTPException) as exc:
        await chat_service.list_messages(
            db_session, conversation.id, "99999999-9999-9999-9999-999999999999"
        )
    assert exc.value.status_code == 403


async def test_paginacao_de_conversas(db_session: AsyncSession, seed_user: str):
    for _ in range(3):
        await chat_service.get_or_create_conversation(db_session, seed_user, None)

    page1, total = await chat_service.list_conversations(db_session, seed_user, page=1, page_size=2)
    page2, _ = await chat_service.list_conversations(db_session, seed_user, page=2, page_size=2)
    assert total == 3
    assert len(page1) == 2
    assert len(page2) == 1
