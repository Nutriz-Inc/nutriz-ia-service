from typing import AsyncIterator

from groq import AsyncGroq

from app.config import settings
from app.llm.provider import LLMProvider


class GroqProvider(LLMProvider):
    def __init__(self) -> None:
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content

    def get_provider_name(self) -> str:
        return "groq"

    def get_model_name(self) -> str:
        return settings.GROQ_MODEL
