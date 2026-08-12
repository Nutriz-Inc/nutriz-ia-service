# Imagem da aplicacao FastAPI do nutriz-ia-service.
# Embeddings via ONNX Runtime (SEM torch): carrega o modelo com vocabulario
# PODADO (~50k tokens PT), gerado FORA do build por scripts/export_model.py +
# scripts/prune_vocab.py. Cabe no free tier. Ver docs/otimizacao-memoria.md.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDINGS_MODEL_DIR=/models \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Artefato de embeddings ja pronto (model.onnx podado + tokenizer.json). O par
# e versionado junto; regerar SEMPRE os dois (ver docs/otimizacao-memoria.md).
COPY models /models

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts
COPY docs/protocolos ./docs/protocolos
COPY docker/entrypoint.sh /entrypoint.sh

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /models /app \
    && chmod +x /entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
