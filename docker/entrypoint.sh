#!/bin/sh
# Entrypoint da aplicacao: aplica migrations, garante os chunks do RAG e sobe
# o servidor. Migrations na subida evitam banco dessincronizado do codigo.
set -e

echo "Aplicando migrations (alembic upgrade head)..."
alembic upgrade head

# Ingestao idempotente (apaga+reinsere por fonte): garante que o RAG tenha os
# protocolos mesmo num banco novo (ex.: primeiro deploy no Render). Nao derruba
# a subida se falhar.
echo "Ingerindo protocolos do RAG..."
python -m scripts.ingest_protocols || echo "AVISO: ingestao do RAG falhou; a EVA sobe assim mesmo"

# Render (e outros PaaS) injetam a porta via $PORT; cai para 8000 no local.
PORT="${PORT:-8000}"
echo "Iniciando servidor na porta ${PORT}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
