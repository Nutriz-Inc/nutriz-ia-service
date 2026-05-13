from abc import ABC, abstractmethod
from typing import AsyncIterator

from app.config import settings


class LLMProvider(ABC):
    @abstractmethod
    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        ...


def get_llm_provider() -> LLMProvider:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "groq":
        from app.llm.groq_provider import GroqProvider
        return GroqProvider()
    if provider == "ollama":
        from app.llm.ollama_provider import OllamaProvider
        return OllamaProvider()
    raise ValueError(
        f"LLM_PROVIDER desconhecido: '{settings.LLM_PROVIDER}'. "
        f"Valores aceitos: 'groq', 'ollama'."
    )
