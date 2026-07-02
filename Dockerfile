# Imagem da aplicacao FastAPI do nutriz-ia-service.
# Python 3.13 slim + torch CPU-only (imagem nao pode inflar com CUDA).

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SENTENCE_TRANSFORMERS_HOME=/models-cache

WORKDIR /app

# torch CPU-only instalado ANTES do requirements: o indice padrao do PyPI
# traria wheels CUDA de varios GB junto com o sentence-transformers
RUN pip install torch==2.12.0+cpu --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts
COPY docs/protocolos ./docs/protocolos
COPY docker/entrypoint.sh /entrypoint.sh

# Usuario nao-root; cache de modelos em volume (ver docs/decisoes.md)
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /models-cache \
    && chown -R appuser:appuser /models-cache /app \
    && chmod +x /entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
