# Testes de integracao do pipeline RAG: ingestao -> busca vetorial -> chunks.
# Embeddings deterministicos (mockados); banco pgvector real de teste.

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.ingest_protocols import chunk_text, ingest_file
from app.services.rag_service import search_chunks


def test_chunk_text_respeita_tamanho_e_overlap():
    palavras = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_text(palavras, chunk_size=400, overlap=50)
    assert len(chunks) == 3
    primeiro = chunks[0].split()
    segundo = chunks[1].split()
    assert len(primeiro) == 400
    # Overlap: as ultimas 50 palavras do chunk 1 sao as primeiras do chunk 2
    assert primeiro[-50:] == segundo[:50]


def test_chunk_text_texto_curto_vira_um_chunk():
    assert chunk_text("texto curto", chunk_size=400, overlap=50) == ["texto curto"]


def test_chunk_text_vazio_retorna_lista_vazia():
    assert chunk_text("   ", chunk_size=400, overlap=50) == []


async def test_ingest_e_busca_retornam_chunk_correto(
    db_session: AsyncSession, tmp_path: Path
):
    protocolo = tmp_path / "protocolo_ordenha.md"
    protocolo.write_text(
        "A ordenha manual do leite humano deve ser feita com as maos higienizadas.",
        encoding="utf-8",
    )
    outro = tmp_path / "protocolo_triagem.md"
    outro.write_text(
        "A triagem de doadoras exige avaliacao de exames e historico de saude.",
        encoding="utf-8",
    )

    await ingest_file(db_session, protocolo)
    await ingest_file(db_session, outro)

    results = await search_chunks(
        db_session,
        "Como fazer a ordenha manual do leite humano?",
        top_k=2,
        min_score=0.0,
    )
    assert len(results) == 2
    assert results[0].source == "protocolo_ordenha"
    assert "ordenha manual" in results[0].content


async def test_reingestao_e_idempotente(db_session: AsyncSession, tmp_path: Path):
    protocolo = tmp_path / "protocolo_x.md"
    protocolo.write_text("Conteudo original do protocolo.", encoding="utf-8")

    await ingest_file(db_session, protocolo)
    await ingest_file(db_session, protocolo)

    total = (
        await db_session.execute(
            text("SELECT count(*) FROM kb_chunks WHERE source = 'protocolo_x'")
        )
    ).scalar_one()
    assert total == 1


async def test_reingestao_atualiza_conteudo(db_session: AsyncSession, tmp_path: Path):
    protocolo = tmp_path / "protocolo_y.md"
    protocolo.write_text("Versao um.", encoding="utf-8")
    await ingest_file(db_session, protocolo)

    protocolo.write_text("Versao dois atualizada.", encoding="utf-8")
    await ingest_file(db_session, protocolo)

    rows = (
        await db_session.execute(
            text("SELECT content FROM kb_chunks WHERE source = 'protocolo_y'")
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].content == "Versao dois atualizada."


async def test_metadata_da_ingestao(db_session: AsyncSession, tmp_path: Path):
    protocolo = tmp_path / "protocolo_meta.md"
    protocolo.write_text("Qualquer conteudo de protocolo.", encoding="utf-8")
    await ingest_file(db_session, protocolo)

    row = (
        await db_session.execute(
            text("SELECT metadata FROM kb_chunks WHERE source = 'protocolo_meta'")
        )
    ).one()
    import json

    metadata = row.metadata if isinstance(row.metadata, dict) else json.loads(row.metadata)
    assert metadata["filename"] == "protocolo_meta.md"
    assert metadata["chunk_index"] == 0
    assert metadata["total_chunks"] == 1
