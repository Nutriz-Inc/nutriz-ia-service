import asyncio
import logging
from typing import Any, AsyncIterator, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.provider import ChamadaDeFerramenta, LLMProvider
from app.services.eva_ferramentas import (
    FERRAMENTAS,
    STATUS_POR_FERRAMENTA,
    Relatorio,
    ResultadoDaFerramenta,
    executar,
)

logger = logging.getLogger(__name__)

RODADAS_COM_FERRAMENTAS = 2
PEDIDO_DE_RESPOSTA_FINAL = {
    "role": "system",
    "content": (
        "Voce ja consultou tudo o que podia. Responda agora so com texto, usando "
        "apenas os dados acima. Se faltar algum dado, diga qual."
    ),
}
FALHA_NA_RESPOSTA_FINAL = (
    "Consultei os dados, mas nao consegui montar a resposta agora. "
    "Pode perguntar de novo?"
)
LIMITE_POR_CONSULTA_SEGUNDOS = 10.0

FALHA_NA_CONSULTA = ResultadoDaFerramenta(
    {
        "erro": (
            "nao foi possivel ler os dados agora. Diga isso em uma frase, "
            "sem estimar numero nenhum, e sugira tentar de novo em instantes."
        )
    }
)

AoStatus = Callable[[str], Awaitable[None]]
AoRelatorio = Callable[[Relatorio], Awaitable[None]]


def _mensagem_de_chamadas(chamadas: list[ChamadaDeFerramenta]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": chamada.id,
                "type": "function",
                "function": {"name": chamada.nome, "arguments": chamada.argumentos or "{}"},
            }
            for chamada in chamadas
        ],
    }


async def _executar_com_limite(
    db: AsyncSession, chamada: ChamadaDeFerramenta
) -> ResultadoDaFerramenta:
    try:
        return await asyncio.wait_for(
            executar(db, chamada.nome, chamada.argumentos),
            timeout=LIMITE_POR_CONSULTA_SEGUNDOS,
        )
    except Exception:
        logger.exception(f"Falha na ferramenta {chamada.nome}")
        await db.rollback()
        return FALHA_NA_CONSULTA


async def responder_com_ferramentas(
    provider: LLMProvider,
    db: AsyncSession,
    messages: list[dict[str, Any]],
    ao_status: AoStatus,
    ao_relatorio: AoRelatorio,
) -> AsyncIterator[str]:
    tentativas_da_primeira = 2
    rodada = 0
    while rodada < RODADAS_COM_FERRAMENTAS:
        chamadas: list[ChamadaDeFerramenta] = []
        enviou = False

        try:
            async for evento in provider.stream_com_ferramentas(
                messages, FERRAMENTAS, obrigar_ferramenta=rodada == 0
            ):
                if evento.texto:
                    enviou = True
                    yield evento.texto
                if evento.chamadas:
                    chamadas = evento.chamadas
        except Exception:
            logger.exception(f"Falha na rodada {rodada} com ferramentas")
            if enviou:
                return
            if rodada == 0 and tentativas_da_primeira > 1:
                tentativas_da_primeira -= 1
                continue
            break

        if not chamadas:
            return

        messages.append(_mensagem_de_chamadas(chamadas))
        for chamada in chamadas:
            await ao_status(STATUS_POR_FERRAMENTA.get(chamada.nome, "Consultando os dados"))
            resultado = await _executar_com_limite(db, chamada)
            if resultado.relatorio is not None:
                await ao_relatorio(resultado.relatorio)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": chamada.id,
                    "content": resultado.para_o_modelo(),
                }
            )
        rodada += 1

    if rodada == 0:
        yield FALHA_NA_RESPOSTA_FINAL
        return

    async for texto in _resposta_final(provider, messages):
        yield texto


async def _resposta_final(
    provider: LLMProvider, messages: list[dict[str, Any]]
) -> AsyncIterator[str]:
    for tentativa in range(2):
        conversa = messages if tentativa == 0 else [*messages, PEDIDO_DE_RESPOSTA_FINAL]
        enviou = False
        try:
            async for evento in provider.stream_com_ferramentas(conversa, None):
                if evento.texto:
                    enviou = True
                    yield evento.texto
            if enviou:
                return
        except Exception:
            logger.exception("Falha na resposta final do modo operacional")
            if enviou:
                return
    yield FALHA_NA_RESPOSTA_FINAL
