from fastapi import HTTPException, WebSocket

from app.services.auth import decode_token


async def authenticate_websocket(
    websocket: WebSocket,
    token: str | None,
) -> str | None:
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return None

    try:
        payload = decode_token(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Invalid token")
        return None

    return payload.id_user
