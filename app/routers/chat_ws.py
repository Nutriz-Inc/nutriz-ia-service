# Endpoint WebSocket de chat com a EVA.
# Autenticacao via query string: ws://host/ws/chat?token=<jwt>

import asyncio
import logging
import time
import traceback
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.llm.provider import get_llm_provider
from app.services import chat_service
from app.services.auth_ws import authenticate_websocket
from app.services.consent_service import has_valid_consent
from app.services.embeddings import embeddings_service
from app.services.eva_prompt import build_messages_for_llm_with_rag
from app.services.latency import PhaseTimer
from app.services.profile_service import get_nutriz_profile
from app.services.rag_service import search_chunks


logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


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
            data = await websocket.receive_json()
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

            rag_chunks = await search_chunks(
                db,
                user_message,
                top_k=4,
                timer=turn_timer,
                query_embedding=query_embedding,
            )

            messages = build_messages_for_llm_with_rag(
                history,
                user_message,
                rag_chunks,
                profile=nutriz_profile,
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

            await websocket.send_json({"type": "done"})
            latency_ms = int((time.time() - start_time) * 1000)
            turn_timer.record("t_llm_total", latency_ms)

            # Persistencia fora do caminho critico: gravar depois do streaming
            # nao atrasa o primeiro token. Ordem user -> assistant preservada.
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
                )

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
