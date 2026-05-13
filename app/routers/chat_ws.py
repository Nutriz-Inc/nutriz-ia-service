# Endpoint WebSocket de chat com a EVA.
# Autenticacao via query string: ws://host/ws/chat?token=<jwt>

from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.llm.provider import get_llm_provider
from app.services import chat_service
from app.services.auth_ws import authenticate_websocket
from app.services.eva_prompt import build_messages_for_llm


router = APIRouter(tags=["chat"])


@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str | None = Query(None),
    conversation_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    await websocket.accept()

    user_id = await authenticate_websocket(websocket, token)
    if user_id is None:
        return

    try:
        conv_uuid = UUID(conversation_id) if conversation_id else None
    except ValueError:
        await websocket.close(code=4002, reason="Invalid conversation_id")
        return

    try:
        conversation = await chat_service.get_or_create_conversation(
            db, user_id, conv_uuid
        )
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close()
        return

    await websocket.send_json(
        {"type": "conversation", "conversation_id": str(conversation.id)}
    )

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message")
            if not user_message:
                await websocket.send_json(
                    {"type": "error", "message": "Missing 'message' field"}
                )
                continue

            history = await chat_service.get_recent_messages(
                db, conversation.id, limit=10
            )
            messages = build_messages_for_llm(history, user_message)

            await chat_service.save_message(
                db, conversation.id, "user", user_message
            )

            provider = get_llm_provider()
            full_response = ""
            async for chunk in provider.stream_chat(messages):
                full_response += chunk
                await websocket.send_json({"type": "chunk", "content": chunk})

            await websocket.send_json({"type": "done"})

            await chat_service.save_message(
                db, conversation.id, "assistant", full_response
            )
    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
        except Exception:
            pass
