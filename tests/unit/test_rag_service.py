# Testes unitarios do servico de RAG: score, ordenacao e threshold.
# Usa o banco de teste com vetores deterministicos (embeddings mockados).

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KbChunk
from app.services.rag_service import MIN_SCORE_THRESHOLD, search_chunks
from tests.conftest import fake_encode


async def _insert_chunk(db: AsyncSession, content: str, source: str = "protocolo_teste") -> None:
    db.add(KbChunk(source=source, content=content, embedding=fake_encode(content)))
    await db.commit()


async def test_score_e_max_zero_um_menos_distancia(db_session: AsyncSession):
    await _insert_chunk(db_session, "ordenha manual do leite humano")

    results = await search_chunks(
        db_session, "ordenha manual do leite humano", top_k=1, min_score=0.0
    )
    assert len(results) == 1
    # Query identica ao chunk: distancia ~0 => score ~1
    assert results[0].score == pytest.approx(1.0, abs=0.01)
    assert 0.0 <= results[0].score <= 1.0


async def test_ordenacao_por_similaridade(db_session: AsyncSession):
    await _insert_chunk(db_session, "armazenamento do leite em freezer domestico")
    await _insert_chunk(db_session, "triagem e selecao de doadoras de leite")

    results = await search_chunks(
        db_session, "como armazenar leite em freezer domestico", top_k=2, min_score=0.0
    )
    assert len(results) == 2
    assert results[0].score >= results[1].score
    assert "freezer" in results[0].content


async def test_chunks_abaixo_do_threshold_sao_descartados(db_session: AsyncSession):
    await _insert_chunk(db_session, "texto completamente sem relacao alguma xyz")

    results = await search_chunks(
        db_session, "ordenha manual leite humano doacao", top_k=4
    )
    # Vetores aleatorios independentes tem similaridade ~0 => score < 0.3
    assert results == []


async def test_threshold_padrao_e_configuravel(db_session: AsyncSession):
    await _insert_chunk(db_session, "texto completamente sem relacao alguma xyz")

    sem_filtro = await search_chunks(
        db_session, "ordenha manual leite humano", top_k=4, min_score=0.0
    )
    assert len(sem_filtro) == 1
    assert sem_filtro[0].score < MIN_SCORE_THRESHOLD


async def test_pergunta_sem_correspondencia_retorna_lista_vazia(db_session: AsyncSession):
    results = await search_chunks(db_session, "qualquer pergunta", top_k=4)
    assert results == []


async def test_respeita_top_k(db_session: AsyncSession):
    for i in range(5):
        await _insert_chunk(db_session, f"ordenha manual do leite variante {i}")

    results = await search_chunks(
        db_session, "ordenha manual do leite", top_k=3, min_score=0.0
    )
    assert len(results) == 3


async def test_indice_de_busca_e_hnsw(db_session: AsyncSession):
    # Paridade com producao: o banco de teste (create_all a partir do model)
    # deve usar hnsw, nao ivfflat. O bug original passou despercebido porque
    # o ivfflat degenerado nunca foi exercitado nesta suite.
    row = (
        await db_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'ix_kb_chunks_embedding'"
            )
        )
    ).scalar_one()
    assert "hnsw" in row.lower()
    assert "vector_cosine_ops" in row.lower()
