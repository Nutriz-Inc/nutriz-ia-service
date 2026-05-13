# Endpoints REST para listar conversas e mensagens do usuario autenticado.

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.conversation import (
    ConversationListResponse,
    ConversationResponse,
    MessageResponse,
)
from app.services import chat_service
from app.services.auth import get_current_user_id


router = APIRouter(tags=["conversations"])


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    conversations, total = await chat_service.list_conversations(
        db, user_id, page, page_size
    )
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(c) for c in conversations],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def list_messages(
    conversation_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    messages = await chat_service.list_messages(db, conversation_id, user_id)
    return [MessageResponse.model_validate(m) for m in messages]
