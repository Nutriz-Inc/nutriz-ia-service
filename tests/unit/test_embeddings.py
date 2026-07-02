# Testes do servico de embeddings com o SentenceTransformer mockado
# (nenhum teste baixa ou carrega o modelo real).

import numpy as np
import pytest

import app.services.embeddings as embeddings_module
from app.services.embeddings import EmbeddingsService


class FakeSentenceTransformer:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def encode(self, data, normalize_embeddings=False, show_progress_bar=False):
        if isinstance(data, list):
            return np.ones((len(data), 384))
        return np.ones(384)


@pytest.fixture
def fresh_service(monkeypatch: pytest.MonkeyPatch):
    # Reseta o singleton para testar carga lazy sem afetar outros testes
    monkeypatch.setattr(embeddings_module, "SentenceTransformer", FakeSentenceTransformer)
    monkeypatch.setattr(EmbeddingsService, "_instance", None)
    monkeypatch.setattr(EmbeddingsService, "_model", None)
    yield EmbeddingsService()
    EmbeddingsService._instance = None
    EmbeddingsService._model = None


def test_singleton_retorna_mesma_instancia(fresh_service: EmbeddingsService):
    assert EmbeddingsService() is fresh_service


def test_modelo_carrega_uma_unica_vez(fresh_service: EmbeddingsService):
    fresh_service.encode("primeiro")
    model = fresh_service._model
    fresh_service.encode("segundo")
    assert fresh_service._model is model


def test_encode_retorna_lista_de_384_floats(fresh_service: EmbeddingsService):
    result = fresh_service.encode("texto")
    assert isinstance(result, list)
    assert len(result) == 384


def test_encode_batch_preserva_ordem_e_tamanho(fresh_service: EmbeddingsService):
    result = fresh_service.encode_batch(["a", "b", "c"])
    assert len(result) == 3
    assert all(len(v) == 384 for v in result)


async def test_encode_async_roda_em_thread(fresh_service: EmbeddingsService):
    result = await fresh_service.encode_async("texto")
    assert len(result) == 384
