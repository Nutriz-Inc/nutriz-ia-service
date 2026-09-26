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
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            extra_body=self._parametros_de_raciocinio(),
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content

    async def aquecer(self) -> None:
        await self.client.models.list()

    def _parametros_de_raciocinio(self) -> dict[str, str] | None:
        if not settings.GROQ_MODEL.startswith("openai/gpt-oss"):
            return None
        return {"reasoning_effort": settings.GROQ_REASONING_EFFORT}

    def get_provider_name(self) -> str:
        return "groq"

    def get_model_name(self) -> str:
        return settings.GROQ_MODEL
