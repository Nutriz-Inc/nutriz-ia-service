#!/bin/sh
# Entrypoint da aplicacao: aplica migrations e sobe o servidor.
# Migrations na subida garantem banco nunca dessincronizado do codigo.
set -e

echo "Aplicando migrations (alembic upgrade head)..."
alembic upgrade head

echo "Iniciando servidor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
