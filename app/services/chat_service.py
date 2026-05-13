from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, LlmAudit, Message


async def get_or_create_conversation(
    db: AsyncSession,
    user_id: str,
    conversation_id: UUID | None,
) -> Conversation:
    if conversation_id is not None:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        if conversation.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Conversation does not belong to user",
            )
        return conversation

    conversation = Conversation(user_id=user_id)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def save_message(
    db: AsyncSession,
    conversation_id: UUID,
    role: str,
    content: str,
    tokens_used: int | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        tokens_used=tokens_used,
    )
    db.add(message)

    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one()
    conversation.last_message_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(message)
    return message


async def get_recent_messages(
    db: AsyncSession,
    conversation_id: UUID,
    limit: int = 10,
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def save_llm_audit(
    db: AsyncSession,
    user_id: str,
    conversation_id: UUID,
    message_id: UUID | None,
    prompt_full: list[dict[str, str]],
    llm_provider: str,
    llm_model: str,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
    latency_ms: int | None = None,
) -> None:
    audit = LlmAudit(
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        prompt_full=prompt_full,
        chunks_used=None,
        llm_provider=llm_provider,
        llm_model=llm_model,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        latency_ms=latency_ms,
    )
    db.add(audit)
    await db.commit()
