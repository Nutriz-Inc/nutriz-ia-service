from abc import ABC, abstractmethod
from functools import lru_cache
from typing import AsyncIterator

from app.config import settings


class LLMProvider(ABC):
    @abstractmethod
    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        ...

    @abstractmethod
    def get_provider_name(self) -> str:
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        ...


# Cache de instancia unica: reinstanciar o provider (e seu client HTTP) a cada
# turno descartava o connection pooling e pagava novo handshake TLS por mensagem.
# Em testes, use get_llm_provider.cache_clear() ao trocar LLM_PROVIDER.
@lru_cache(maxsize=1)
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
