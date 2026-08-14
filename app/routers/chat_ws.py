# Endpoint WebSocket de chat com a EVA.
# Autenticacao via query string: ws://host/ws/chat?token=<jwt>

import asyncio
import json
import logging
import time
import traceback
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.llm.provider import get_llm_provider
from app.services import chat_service, public_guard
from app.services.action_service import detect_action
from app.services.auth_ws import authenticate_websocket
from app.services.consent_service import has_valid_consent
from app.services.embeddings import embeddings_service
from app.services.eva_prompt import (
    build_messages_for_llm_with_rag,
    build_messages_for_public_llm,
)
from app.services.latency import PhaseTimer
from app.services.profile_service import (
    STAFF_USER_TYPES,
    get_nutriz_profile,
    get_user_type,
)
from app.services.rag_service import search_chunks
from app.services.rate_limiter import rate_limiter
from app.services.session_service import decode_anonymous_session, hash_ip
from app.config import settings


logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _client_ip(websocket: WebSocket) -> str:
    # Atras de proxy reverso o IP real vem no X-Forwarded-For (primeiro da lista)
    forwarded = websocket.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if websocket.client is not None:
        return websocket.client.host
    return "unknown"


@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str | None = Query(None),
    conversation_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    await websocket.accept()

    setup_timer = PhaseTimer()

    with setup_timer.measure("t_auth"):
        user_id = await authenticate_websocket(websocket, token)
    if user_id is None:
        return

    # Staff (adm/nurse) nao usa a EVA: recusa no backend, nao apenas na UI.
    # Usuario sem linha na tabela user segue permitido (mesma postura do
    # perfil: em dev o espelho pode nao ter o registro; o chat degrada sem
    # personalizacao em vez de bloquear a nutriz).
    with setup_timer.measure("t_role"):
        user_type = await get_user_type(db, user_id)
    if user_type in STAFF_USER_TYPES:
        await websocket.send_json({
            "type": "error",
            "code": "staff_not_allowed",
            "message": "A EVA atende apenas nutrizes. Perfis administrativos nao tem acesso ao chat.",
        })
        await websocket.close(code=4403, reason="Staff role not allowed")
        return

    with setup_timer.measure("t_consent"):
        has_consent = await has_valid_consent(db, user_id)
    if not has_consent:
        await websocket.send_json({
            "type": "error",
            "code": "lgpd_consent_required",
            "message": "E necessario aceitar os termos de uso antes de iniciar o chat.",
        })
        await websocket.close(code=4003, reason="LGPD consent required")
        return

    try:
        conv_uuid = UUID(conversation_id) if conversation_id else None
    except ValueError:
        await websocket.close(code=4002, reason="Invalid conversation_id")
        return

    try:
        with setup_timer.measure("t_conversation"):
            conversation = await chat_service.get_or_create_conversation(
                db, user_id, conv_uuid
            )
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"Erro ao criar/recuperar conversa: {error_msg}")
        logger.error(traceback.format_exc())
        await websocket.send_json({"type": "error", "message": error_msg})
        await websocket.close()
        return

    await websocket.send_json(
        {"type": "conversation", "conversation_id": str(conversation.id)}
    )

    with setup_timer.measure("t_profile"):
        nutriz_profile = await get_nutriz_profile(db, user_id)
    if nutriz_profile is None:
        logger.warning(f"Perfil nao encontrado para user_id={user_id}, EVA seguira sem personalizacao")

    setup_timer.log_summary(f"setup conexao user={user_id}")

    # Provider resolvido uma vez por conexao (instancia cacheada no modulo)
    provider = get_llm_provider()

    try:
        while True:
            # JSON invalido ou payload que nao e objeto nao pode derrubar a
            # conexao: responde erro estruturado e segue aguardando
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "message": "Invalid JSON payload"}
                )
                continue
            if not isinstance(data, dict):
                await websocket.send_json(
                    {"type": "error", "message": "Payload must be a JSON object"}
                )
                continue

            user_message = data.get("message")
            if not user_message:
                await websocket.send_json(
                    {"type": "error", "message": "Missing 'message' field"}
                )
                continue

            turn_timer = PhaseTimer()

            # Encode do embedding (CPU em thread) e busca do historico (I/O no
            # banco) sao independentes: rodam em paralelo. Nao e possivel
            # paralelizar duas queries na mesma AsyncSession, mas encode nao usa
            # a sessao.
            with turn_timer.measure("t_history_e_embedding"):
                history, query_embedding = await asyncio.gather(
                    chat_service.get_recent_messages(db, conversation.id, limit=10),
                    embeddings_service.encode_async(user_message),
                )

            # top-3 (era top-4): menos tokens de input = primeiro token mais
            # rapido no Groq, sem perda relevante de contexto no RAG
            rag_chunks = await search_chunks(
                db,
                user_message,
                top_k=3,
                timer=turn_timer,
                query_embedding=query_embedding,
            )

            # Acao contextual por regras (nunca pelo LLM). Detectada ANTES de
            # montar o prompt: quando ha acao, a resposta deve ser curta e
            # apontar para o botao. Nutriz logada nao e anonima: signup/login
            # nunca disparam.
            action = detect_action(user_message, is_anonymous=False)

            messages = build_messages_for_llm_with_rag(
                history,
                user_message,
                rag_chunks,
                profile=nutriz_profile,
                action_label=action.label if action else None,
            )

            start_time = time.time()
            first_token_at: float | None = None
            full_response = ""
            async for chunk in provider.stream_chat(messages):
                if first_token_at is None:
                    first_token_at = time.time()
                    turn_timer.record(
                        "t_llm_first_token", (first_token_at - start_time) * 1000
                    )
                full_response += chunk
                await websocket.send_json({"type": "chunk", "content": chunk})

            latency_ms = int((time.time() - start_time) * 1000)
            turn_timer.record("t_llm_total", latency_ms)

            # Persistencia fora do caminho critico do PRIMEIRO token: grava
            # depois de todos os chunks, mas ANTES do "done" - se o cliente
            # desconectar apos o done, nada se perde (llm_audit e obrigatorio).
            with turn_timer.measure("t_persist_user_msg"):
                await chat_service.save_message(
                    db, conversation.id, "user", user_message
                )

            with turn_timer.measure("t_persist_assistant"):
                assistant_message = await chat_service.save_message(
                    db, conversation.id, "assistant", full_response
                )

            chunks_used_audit = [
                {
                    "source": c.source,
                    "score": c.score,
                    "preview": c.content[:200],
                }
                for c in rag_chunks
            ]

            with turn_timer.measure("t_persist_audit"):
                await chat_service.save_llm_audit(
                    db=db,
                    user_id=user_id,
                    conversation_id=conversation.id,
                    message_id=assistant_message.id,
                    prompt_full=messages,
                    llm_provider=provider.get_provider_name(),
                    llm_model=provider.get_model_name(),
                    latency_ms=latency_ms,
                    chunks_used=chunks_used_audit,
                    action_emitted=action.slug if action else None,
                )

            if action is not None:
                await websocket.send_json(
                    {"type": "action", "action": action.slug, "label": action.label}
                )

            await websocket.send_json({"type": "done"})

            turn_timer.log_summary(f"turno conversa={conversation.id}")
    except WebSocketDisconnect:
        return
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"Erro no websocket_chat: {error_msg}")
        logger.error(traceback.format_exc())
        try:
            await websocket.send_json({"type": "error", "message": error_msg})
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/chat-public")
async def websocket_chat_public(
    websocket: WebSocket,
    token: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    await websocket.accept()

    payload = decode_anonymous_session(token) if token else None
    if payload is None:
        await websocket.close(code=4001, reason="Invalid anonymous session")
        return

    session_id = payload.session_id
    ip_hash = hash_ip(_client_ip(websocket))

    # Sem persistencia: a conversa vive apenas na memoria desta conexao. O
    # frame conversation reusa o session_id para o front seguir o mesmo fluxo.
    await websocket.send_json({"type": "conversation", "conversation_id": session_id})

    provider = get_llm_provider()
    history: list[dict[str, str]] = []
    jailbreak_strikes = 0

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "message": "Invalid JSON payload"}
                )
                continue
            if not isinstance(data, dict):
                await websocket.send_json(
                    {"type": "error", "message": "Payload must be a JSON object"}
                )
                continue

            user_message = data.get("message")
            if not user_message:
                await websocket.send_json(
                    {"type": "error", "message": "Missing 'message' field"}
                )
                continue

            # PII: dado sensivel do visitante nunca chega ao LLM nem e auditado.
            if public_guard.contains_pii(user_message):
                await _stream_static_reply(websocket, public_guard.PII_WARNING)
                continue

            # Anti-jailbreak: acumula strikes; ao 3o, encerra a sessao.
            if public_guard.is_jailbreak_attempt(user_message):
                jailbreak_strikes += 1
                if jailbreak_strikes >= settings.ANON_MAX_JAILBREAK_STRIKES:
                    await _stream_static_reply(
                        websocket, public_guard.JAILBREAK_SESSION_ENDED
                    )
                    await websocket.close(code=4008, reason="Jailbreak limit")
                    return
                await _stream_static_reply(websocket, public_guard.JAILBREAK_WARNING)
                continue

            allowed, reason = await rate_limiter.check_and_increment(ip_hash, session_id)
            if not allowed:
                await _stream_static_reply(
                    websocket, _rate_limit_message(reason)
                )
                await websocket.close(code=4029, reason="Rate limit exceeded")
                return

            query_embedding = await embeddings_service.encode_async(user_message)
            # top-2 no modo publico: economia de tokens de input no free tier
            rag_chunks = await search_chunks(
                db, user_message, top_k=2, query_embedding=query_embedding
            )

            # Acao contextual por regras, detectada antes do prompt: com acao, a
            # resposta e curta e aponta para o botao. Modo anonimo: signup/login
            # podem disparar.
            action = detect_action(user_message, is_anonymous=True)

            messages = build_messages_for_public_llm(
                history, user_message, rag_chunks, action_label=action.label if action else None
            )

            start_time = time.time()
            full_response = ""
            async for chunk in provider.stream_chat(messages):
                full_response += chunk
                await websocket.send_json({"type": "chunk", "content": chunk})

            latency_ms = int((time.time() - start_time) * 1000)

            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": full_response})
            # Memoria curta limitada: mesmas ultimas 10 mensagens do chat logado
            history[:] = history[-10:]

            chunks_used_audit = [
                {"source": c.source, "score": c.score, "preview": c.content[:200]}
                for c in rag_chunks
            ]

            # Auditoria LGPD tambem no modo publico: sem user_id, com
            # session_id e ip_hash. Sem persistir conversation/message.
            await chat_service.save_llm_audit(
                db=db,
                user_id=None,
                conversation_id=None,
                message_id=None,
                prompt_full=messages,
                llm_provider=provider.get_provider_name(),
                llm_model=provider.get_model_name(),
                latency_ms=latency_ms,
                chunks_used=chunks_used_audit,
                is_anonymous=True,
                session_id=session_id,
                ip_hash=ip_hash,
                action_emitted=action.slug if action else None,
            )

            if action is not None:
                await websocket.send_json(
                    {"type": "action", "action": action.slug, "label": action.label}
                )

            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        return
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"Erro no websocket_chat_public: {error_msg}")
        logger.error(traceback.format_exc())
        try:
            await websocket.send_json({"type": "error", "message": error_msg})
            await websocket.close()
        except Exception:
            pass


async def _stream_static_reply(websocket: WebSocket, text: str) -> None:
    # Resposta canonica da EVA (guard-rail) no mesmo formato do streaming do LLM,
    # para o front nao precisar de caminho especial.
    await websocket.send_json({"type": "chunk", "content": text})
    await websocket.send_json({"type": "done"})


def _rate_limit_message(reason: str | None) -> str:
    if reason == "ip_hour":
        return (
            "Voce atingiu o limite de mensagens por hora neste chat publico. "
            "Para conversar sem limites e com atendimento personalizado, faca "
            "seu cadastro na plataforma Nutriz. Ate breve!"
        )
    return (
        "Chegamos ao limite desta conversa publica. Para continuar com um "
        "atendimento personalizado e seguro, faca seu cadastro na plataforma "
        "Nutriz. Foi um prazer ajudar!"
    )
