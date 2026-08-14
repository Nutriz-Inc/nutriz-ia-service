# Testes do servico de embeddings com o pipeline ONNX (onnxruntime + tokenizer)
# mockado - nenhum teste carrega o modelo real.

import numpy as np
import pytest

from app.services.embeddings import EmbeddingsService


class _FakeEncoding:
    def __init__(self, n: int) -> None:
        self.ids = [1] * n
        self.attention_mask = [1] * n


class _FakeTokenizer:
    def enable_truncation(self, max_length: int) -> None:
        pass

    def enable_padding(self) -> None:
        pass

    def encode_batch(self, texts):
        return [_FakeEncoding(5) for _ in texts]


class _FakeInput:
    name = "input_ids"


class _FakeSession:
    def get_inputs(self):
        return [_FakeInput()]

    def run(self, _out, feed):
        batch, seq = feed["input_ids"].shape
        # last_hidden_state [batch, seq, 384] com valores != 1 para exercitar
        # o mean pooling + normalizacao L2.
        return [np.full((batch, seq, 384), 2.0, dtype=np.float32)]


@pytest.fixture
def fresh_service(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(EmbeddingsService, "_instance", None)
    monkeypatch.setattr(EmbeddingsService, "_session", None)
    monkeypatch.setattr(EmbeddingsService, "_tokenizer", None)

    def fake_load(self):
        if self._session is None:
            self._session = _FakeSession()
            self._tokenizer = _FakeTokenizer()
            self._input_names = {"input_ids"}

    monkeypatch.setattr(EmbeddingsService, "_load", fake_load)
    service = EmbeddingsService()
    yield service
    EmbeddingsService._instance = None
    EmbeddingsService._session = None
    EmbeddingsService._tokenizer = None


def test_singleton_retorna_mesma_instancia(fresh_service: EmbeddingsService):
    assert EmbeddingsService() is fresh_service


def test_modelo_carrega_uma_unica_vez(fresh_service: EmbeddingsService):
    fresh_service.encode("primeiro")
    session = fresh_service._session
    fresh_service.encode("segundo")
    assert fresh_service._session is session


def test_encode_retorna_lista_de_384_floats(fresh_service: EmbeddingsService):
    result = fresh_service.encode("texto")
    assert isinstance(result, list)
    assert len(result) == 384


def test_encode_normaliza_para_norma_unitaria(fresh_service: EmbeddingsService):
    result = fresh_service.encode("texto")
    assert np.isclose(np.linalg.norm(result), 1.0, atol=1e-5)


def test_encode_batch_preserva_ordem_e_tamanho(fresh_service: EmbeddingsService):
    result = fresh_service.encode_batch(["a", "b", "c"])
    assert len(result) == 3
    assert all(len(v) == 384 for v in result)


async def test_encode_async_roda_em_thread(fresh_service: EmbeddingsService):
    result = await fresh_service.encode_async("texto")
    assert len(result) == 384
