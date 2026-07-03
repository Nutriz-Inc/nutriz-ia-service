# Endpoint de sessao anonima do modo publico.
# Emite um session token curto para o visitante da landing usar no
# /ws/chat-public. Sem autenticacao previa (e o ponto de entrada anonimo).

from fastapi import APIRouter

from app.services.session_service import AnonSessionToken, create_anonymous_session


router = APIRouter(tags=["session"])


@router.post("/session/anonymous", response_model=AnonSessionToken)
async def create_anonymous_session_endpoint() -> AnonSessionToken:
    return create_anonymous_session()
