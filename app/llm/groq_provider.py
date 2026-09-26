import logging
from typing import Any, AsyncIterator

from groq import NOT_GIVEN, AsyncGroq, RateLimitError

from app.config import settings
from app.llm.provider import ChamadaDeFerramenta, EventoDoModelo, LLMProvider

logger = logging.getLogger(__name__)


def parametros_de_raciocinio(modelo: str) -> dict[str, str] | None:
    if modelo.startswith("qwen/"):
        return {"reasoning_effort": "none"}
    if modelo.startswith("openai/gpt-oss"):
        return {"reasoning_effort": settings.GROQ_REASONING_EFFORT}
    return None


def modelos_em_ordem() -> list[str]:
    reservas = [
        modelo.strip()
        for modelo in settings.GROQ_MODELOS_RESERVA.split(",")
        if modelo.strip() and modelo.strip() != settings.GROQ_MODEL
    ]
    return [settings.GROQ_MODEL, *reservas]


class GroqProvider(LLMProvider):
    def __init__(self) -> None:
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    async def _criar_stream(self, **parametros: Any):
        modelos = modelos_em_ordem()
        for indice, modelo in enumerate(modelos):
            ultimo = indice == len(modelos) - 1
            cliente = self.client if ultimo else self.client.with_options(max_retries=0)
            try:
                return await cliente.chat.completions.create(
                    model=modelo,
                    stream=True,
                    max_tokens=settings.LLM_MAX_TOKENS,
                    temperature=settings.LLM_TEMPERATURE,
                    extra_body=parametros_de_raciocinio(modelo),
                    **parametros,
                )
            except RateLimitError:
                if ultimo:
                    raise
                logger.warning(
                    f"Groq no limite de tokens para {modelo}; seguindo com {modelos[indice + 1]}"
                )
        raise RuntimeError("nenhum modelo configurado")

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        stream = await self._criar_stream(messages=messages)
        async for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content

    async def stream_com_ferramentas(
        self,
        messages: list[dict[str, Any]],
        ferramentas: list[dict[str, Any]] | None,
        obrigar_ferramenta: bool = False,
    ) -> AsyncIterator[EventoDoModelo]:
        stream = await self._criar_stream(
            messages=messages,
            tools=ferramentas or NOT_GIVEN,
            tool_choice="required" if ferramentas and obrigar_ferramenta else NOT_GIVEN,
        )
        parciais: dict[int, dict[str, str]] = {}
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield EventoDoModelo(texto=delta.content)
            for chamada in delta.tool_calls or []:
                parcial = parciais.setdefault(
                    chamada.index, {"id": "", "nome": "", "argumentos": ""}
                )
                if chamada.id:
                    parcial["id"] = chamada.id
                if chamada.function and chamada.function.name:
                    parcial["nome"] += chamada.function.name
                if chamada.function and chamada.function.arguments:
                    parcial["argumentos"] += chamada.function.arguments

        if parciais:
            yield EventoDoModelo(
                chamadas=[
                    ChamadaDeFerramenta(
                        id=parcial["id"] or f"chamada_{indice}",
                        nome=parcial["nome"],
                        argumentos=parcial["argumentos"],
                    )
                    for indice, parcial in sorted(parciais.items())
                ]
            )

    async def aquecer(self) -> None:
        await self.client.models.list()

    def get_provider_name(self) -> str:
        return "groq"

    def get_model_name(self) -> str:
        return settings.GROQ_MODEL
