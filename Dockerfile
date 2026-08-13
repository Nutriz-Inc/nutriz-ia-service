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

# Artefato de embeddings (model.onnx podado + tokenizer.json) baixado do GitHub
# Release e verificado por SHA-256. O par e versionado junto sob a mesma tag;
# regerar SEMPRE os dois (scripts/export_model.py + prune_vocab.py). Ver
# docs/deploy.md e docs/otimizacao-memoria.md. O binario NAO fica no Git
# (gitignored) por causa do limite de 100 MB/arquivo do GitHub.
ARG EMBEDDINGS_RELEASE=embeddings-v1
ARG MODEL_URL=https://github.com/Nutriz-Inc/nutriz-ia-service/releases/download/${EMBEDDINGS_RELEASE}/model.onnx
ARG TOKENIZER_URL=https://github.com/Nutriz-Inc/nutriz-ia-service/releases/download/${EMBEDDINGS_RELEASE}/tokenizer.json
ARG MODEL_SHA256=8bbc8d80fe3f829db1160f201049825311201ddfbddf22a143efe0908b2eb0a8
ARG TOKENIZER_SHA256=ab94abc7b08e3b3a41c90708e96336a0523cb4cd2ebd5fe37be32729d15b8756
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && mkdir -p /models \
    && curl -fSL "$MODEL_URL" -o /models/model.onnx \
    && curl -fSL "$TOKENIZER_URL" -o /models/tokenizer.json \
    && echo "${MODEL_SHA256}  /models/model.onnx" | sha256sum -c - \
    && echo "${TOKENIZER_SHA256}  /models/tokenizer.json" | sha256sum -c - \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

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
