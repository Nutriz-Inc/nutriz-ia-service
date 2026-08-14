# Servico de busca semantica em kb_chunks.
# Recebe pergunta, gera embedding, busca top-K chunks mais similares.
# Usa cosine distance do pgvector (alinhado com indice ivfflat).

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KbChunk
from app.schemas.rag import ChunkSearchResult
from app.services.embeddings import embeddings_service
from app.services.latency import PhaseTimer


logger = logging.getLogger(__name__)


# Chunks com score abaixo do minimo sao descartados: injetar chunk irrelevante
# infla o prompt (mais latencia no LLM) e pode induzir resposta fora de contexto.
MIN_SCORE_THRESHOLD = 0.3


async def search_chunks(
    db: AsyncSession,
    query: str,
    top_k: int = 4,
    timer: PhaseTimer | None = None,
    query_embedding: list[float] | None = None,
    min_score: float = MIN_SCORE_THRESHOLD,
) -> list[ChunkSearchResult]:
    # Embedding pode vir pre-computado (calculado em paralelo com outro I/O
    # pelo chamador). Se nao vier, calcula aqui.
    if query_embedding is None:
        start = time.perf_counter()
        query_embedding = await embeddings_service.encode_async(query)
        if timer is not None:
            timer.record("t_embedding", (time.perf_counter() - start) * 1000)

    distance = KbChunk.embedding.cosine_distance(query_embedding)

    stmt = (
        select(KbChunk, distance.label("distance"))
        .order_by(distance)
        .limit(top_k)
    )

    start = time.perf_counter()
    result = await db.execute(stmt)
    rows = result.all()
    if timer is not None:
        timer.record("t_rag_sql", (time.perf_counter() - start) * 1000)

    search_results: list[ChunkSearchResult] = []
    for chunk, distance_value in rows:
        score = max(0.0, 1.0 - float(distance_value))
        if score < min_score:
            continue
        search_results.append(
            ChunkSearchResult(
                content=chunk.content,
                source=chunk.source,
                score=score,
                metadata_json=chunk.metadata_json,
            )
        )

    logger.info(
        f"Busca semantica retornou {len(search_results)} chunks para query: '{query[:50]}...'"
    )
    return search_results
