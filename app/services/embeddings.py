# Servico de embeddings para o RAG.
# Pipeline ONNX proprio (onnxruntime + tokenizers), SEM torch e SEM fastembed:
# carrega um modelo int8 embarcado na imagem e reproduz o comportamento do
# sentence-transformers original (mesmo modelo, mean pooling, L2, seq 128).
# Torch foi removido para caber no free tier (ver docs/otimizacao-memoria.md).
# Singleton: sessao carrega uma vez e fica em memoria.

import asyncio
import logging
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from app.config import settings


logger = logging.getLogger(__name__)

# Mesmo max_seq_length do sentence-transformers para este modelo: truncar em
# outro valor muda o embedding de chunks longos (base != query).
MAX_SEQ_LEN = 128


class EmbeddingsService:
    _instance: "EmbeddingsService | None" = None
    _session: ort.InferenceSession | None = None
    _tokenizer: Tokenizer | None = None
    _input_names: set[str] = set()

    def __new__(cls) -> "EmbeddingsService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load(self) -> None:
        if self._session is not None:
            return
        model_dir = Path(settings.EMBEDDINGS_MODEL_DIR)
        logger.info(f"Carregando modelo de embeddings (ONNX int8): {model_dir}")
        so = ort.SessionOptions()
        # Arena e mem_pattern desligados: o allocator padrao pre-aloca pools
        # grandes; para 1 inferencia leve por vez isso so custa RAM.
        so.enable_cpu_mem_arena = False
        so.enable_mem_pattern = False
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_dir / "model.onnx"),
            so,
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {i.name for i in self._session.get_inputs()}
        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=MAX_SEQ_LEN)
        self._tokenizer.enable_padding()
        logger.info("Modelo de embeddings carregado")

    def _embed_batch(self, texts: list[str]) -> np.ndarray:
        self._load()
        assert self._session is not None and self._tokenizer is not None
        encoded = self._tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        feed: dict[str, np.ndarray] = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = np.zeros_like(ids)
        last_hidden = self._session.run(None, feed)[0]  # [batch, seq, 384]
        # Mean pooling ponderado pela mascara + normalizacao L2 (identico ao
        # sentence-transformers com normalize_embeddings=True).
        m = mask[..., None].astype(np.float32)
        summed = (last_hidden * m).sum(axis=1)
        counts = np.clip(m.sum(axis=1), 1e-9, None)
        pooled = summed / counts
        norms = np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
        return (pooled / norms).astype(np.float32)

    def encode(self, text: str) -> list[float]:
        return self._embed_batch([text])[0].tolist()

    def encode_batch(self, texts: list[str], show_progress: bool = False) -> list[list[float]]:
        return [v.tolist() for v in self._embed_batch(texts)]

    async def encode_async(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.encode, text)


embeddings_service = EmbeddingsService()
