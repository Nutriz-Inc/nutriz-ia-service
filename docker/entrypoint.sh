#!/bin/sh
# Entrypoint da aplicacao. Migrations e ingestao sao opcionais via env, para
# nao tocar em banco de producao gerenciado a mao (ex.: Neon compartilhado com
# o backend Go, onde o schema e criado via docs/migracao-neon.sql).
#   RUN_MIGRATIONS=true|false  (default true)  -> alembic upgrade head na subida
#   RUN_INGESTION=true|false   (default false) -> carga dos protocolos do RAG
# No Render ambos ficam false: schema e ingestao sao passos manuais/one-off.
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Aplicando migrations (alembic upgrade head)..."
    alembic upgrade head
else
    echo "RUN_MIGRATIONS=false: pulando migrations (schema gerenciado externamente)."
fi

if [ "${RUN_INGESTION:-false}" = "true" ]; then
    echo "Ingerindo protocolos do RAG..."
    python -m scripts.ingest_protocols || echo "AVISO: ingestao do RAG falhou; a EVA sobe assim mesmo"
else
    echo "RUN_INGESTION=false: pulando ingestao (rodar uma vez a parte)."
fi

# Render (e outros PaaS) injetam a porta via $PORT; cai para 8000 no local.
PORT="${PORT:-8000}"
echo "Iniciando servidor na porta ${PORT}..."
# --proxy-headers + --forwarded-allow-ips="*": atras do proxy reverso do Render,
# confia no X-Forwarded-For/Proto para o IP e o esquema corretos (rate limit e
# ip_hash do modo publico dependem do IP real).
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" \
    --proxy-headers --forwarded-allow-ips="*"
