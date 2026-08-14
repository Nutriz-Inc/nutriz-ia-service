# syntax=docker/dockerfile:1
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
# Release PRIVADO via API de assets, autenticado por um PAT fine-grained
# (Contents: read, so este repo). O token vem como BUILD SECRET (mount), nunca
# ARG: nao fica em layer, historico da imagem nem log de build. Apos baixar,
# confere o SHA-256 (o par tem que casar; ARGs sobreponiveis). Local:
#   DOCKER_BUILDKIT=1 docker build --secret id=gh_token,src=./gh_token.txt .
# Render: cadastrar um Secret File chamado gh_token com o PAT. Ver docs/deploy.md.
ARG EMBEDDINGS_RELEASE=embeddings-v1
ARG GITHUB_REPO=Nutriz-Inc/nutriz-ia-service
ARG MODEL_SHA256=8bbc8d80fe3f829db1160f201049825311201ddfbddf22a143efe0908b2eb0a8
ARG TOKENIZER_SHA256=ab94abc7b08e3b3a41c90708e96336a0523cb4cd2ebd5fe37be32729d15b8756
RUN --mount=type=secret,id=gh_token,dst=/etc/secrets/gh_token \
    apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && mkdir -p /models \
    && TOKEN="$(cat /etc/secrets/gh_token)" \
    && REL="$(curl -fsSL -H "Authorization: Bearer ${TOKEN}" \
         -H "Accept: application/vnd.github+json" \
         "https://api.github.com/repos/${GITHUB_REPO}/releases/tags/${EMBEDDINGS_RELEASE}")" \
    && for name in model.onnx tokenizer.json; do \
         asset_url="$(printf '%s' "$REL" | ASSET="$name" python3 -c \
           "import sys,json,os; d=json.load(sys.stdin); print(next(a['url'] for a in d['assets'] if a['name']==os.environ['ASSET']))")" \
         && curl -fsSL -H "Authorization: Bearer ${TOKEN}" \
              -H "Accept: application/octet-stream" "$asset_url" -o "/models/$name"; \
       done \
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
