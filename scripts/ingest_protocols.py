# Script de ingestao de protocolos em markdown.
# Le todos os .md em docs/protocolos/, quebra em chunks (400 palavras, 50 overlap),
# gera embeddings via sentence-transformers e persiste em kb_chunks.
#
# Idempotente por source: re-ingerir o mesmo arquivo apaga os chunks anteriores
# daquele source e insere os novos.
#
# Uso: python -m scripts.ingest_protocols

import asyncio
import logging
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import KbChunk
from app.services.embeddings import embeddings_service


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


PROTOCOLS_DIR = Path("docs/protocolos")
CHUNK_SIZE_WORDS = 400
CHUNK_OVERLAP_WORDS = 50


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    words = text.split()
    if len(words) <= chunk_size:
        return [text] if text.strip() else []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        if end >= len(words):
            break
        start = end - overlap
    return chunks


async def ingest_file(db: AsyncSession, file_path: Path) -> int:
    source = file_path.stem
    content = file_path.read_text(encoding="utf-8")

    chunks = chunk_text(content, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS)
    if not chunks:
        logger.warning(f"Arquivo {file_path.name} esta vazio, pulando")
        return 0

    logger.info(f"Apagando chunks anteriores de source='{source}'")
    await db.execute(delete(KbChunk).where(KbChunk.source == source))

    logger.info(f"Gerando embeddings para {len(chunks)} chunks de {file_path.name}")
    embeddings = embeddings_service.encode_batch(chunks, show_progress=True)

    for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
        kb_chunk = KbChunk(
            source=source,
            content=chunk_content,
            embedding=embedding,
            metadata_json={
                "filename": file_path.name,
                "chunk_index": index,
                "total_chunks": len(chunks),
            },
        )
        db.add(kb_chunk)

    await db.commit()
    logger.info(f"Persistidos {len(chunks)} chunks de {file_path.name}")
    return len(chunks)


async def main() -> None:
    if not PROTOCOLS_DIR.exists():
        logger.error(f"Diretorio {PROTOCOLS_DIR} nao encontrado")
        return

    md_files = sorted(PROTOCOLS_DIR.glob("*.md"))
    if not md_files:
        logger.warning(f"Nenhum .md encontrado em {PROTOCOLS_DIR}")
        return

    logger.info(f"Encontrados {len(md_files)} arquivos para ingerir")
    total_chunks = 0

    async with async_session_maker() as db:
        for file_path in md_files:
            count = await ingest_file(db, file_path)
            total_chunks += count

    logger.info(f"Ingestao concluida: {total_chunks} chunks no total")


if __name__ == "__main__":
    asyncio.run(main())
