# Servico de busca semantica em kb_chunks.
# Recebe pergunta, gera embedding, busca top-K chunks mais similares.
# Usa cosine distance do pgvector (alinhado com indice ivfflat).

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KbChunk
from app.schemas.rag import ChunkSearchResult
from app.services.embeddings import embeddings_service


logger = logging.getLogger(__name__)


async def search_chunks(
    db: AsyncSession,
    query: str,
    top_k: int = 4,
) -> list[ChunkSearchResult]:
    query_embedding = await embeddings_service.encode_async(query)

    distance = KbChunk.embedding.cosine_distance(query_embedding)

    stmt = (
        select(KbChunk, distance.label("distance"))
        .order_by(distance)
        .limit(top_k)
    )

    result = await db.execute(stmt)
    rows = result.all()

    search_results: list[ChunkSearchResult] = []
    for chunk, distance_value in rows:
        score = max(0.0, 1.0 - float(distance_value))
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
