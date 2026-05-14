# Servico de embeddings para o RAG.
# Usa sentence-transformers com modelo multilingual.
# Singleton: modelo carrega uma vez e fica em memoria.

import asyncio
import logging

from sentence_transformers import SentenceTransformer

from app.config import settings


logger = logging.getLogger(__name__)


class EmbeddingsService:
    _instance: "EmbeddingsService | None" = None
    _model: SentenceTransformer | None = None

    def __new__(cls) -> "EmbeddingsService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info(f"Carregando modelo de embeddings: {settings.EMBEDDING_MODEL}")
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            logger.info("Modelo de embeddings carregado")
        return self._model

    def encode(self, text: str) -> list[float]:
        model = self._get_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def encode_batch(self, texts: list[str], show_progress: bool = False) -> list[list[float]]:
        model = self._get_model()
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
        )
        return embeddings.tolist()

    async def encode_async(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.encode, text)


embeddings_service = EmbeddingsService()
