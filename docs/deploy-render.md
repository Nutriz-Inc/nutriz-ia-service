# Deploy do nutriz-ia-service no Render

O IA service (EVA) valida o JWT emitido pelo backend Go e conversa com o front
por WebSocket. Para funcionar como planejado, tres coisas precisam estar
alinhadas em producao: **o segredo do JWT**, o **CORS** e a **URL do IA no
front**.

## 1. Pre-requisitos
- Um banco **PostgreSQL 16 com a extensao `pgvector`** (o Render oferece;
  a migration inicial roda `CREATE EXTENSION IF NOT EXISTS vector`).
- Uma chave do **Groq** (`GROQ_API_KEY`).
- **Memoria**: a EVA carrega torch + o modelo de embeddings (~470 MB) em RAM.
  O plano **free (512 MB) estoura (OOM)** — use **standard (2 GB)** ou maior.

## 2. Variaveis de ambiente do IA service (no Render)
| Variavel | Valor |
|---|---|
| `DATABASE_URL` | URL do Postgres do Render (pode vir como `postgres://...`; o app converte para asyncpg sozinho) |
| `JWT_SECRET` | **IDENTICO ao `AUTH_JWT_SECRET` do backend Go** ⚠️ |
| `JWT_ALGORITHM` | `HS256` |
| `LLM_PROVIDER` | `groq` |
| `GROQ_API_KEY` | sua chave do Groq |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` |
| `CORS_ALLOW_ORIGINS` | origin(s) do front publicado, separados por virgula (ex.: `https://nutriz-web.onrender.com`) |
| `APP_ENV` | `production` |
| `LOG_LEVEL` | `INFO` |

> ⚠️ **O erro "sessao expirada" no modo logado é quase sempre `JWT_SECRET`
> diferente do `AUTH_JWT_SECRET` do Go.** O Go assina o token; o IA so valida.
> Se os dois nao forem a mesma string, o IA rejeita o token (close 4001).
> Pegue o valor no painel do backend Go (Environment) e cole aqui igual.

## 3. Subida
- Via **Blueprint**: o `render.yaml` na raiz cria o web service (Docker) + o
  Postgres. Depois preencha os `sync: false` (`JWT_SECRET`, `GROQ_API_KEY`,
  `CORS_ALLOW_ORIGINS`).
- O `entrypoint.sh` roda `alembic upgrade head`, ingere os protocolos do RAG
  (idempotente) e sobe o uvicorn na porta do Render (`$PORT`).
- Health check: `GET /health`.

## 4. Ajustar o front (web-nutriz)
No build de producao do front, apontar para o IA publicado:
```
VITE_EVA_WS_URL=wss://nutriz-ia-service.onrender.com
VITE_EVA_API_URL=https://nutriz-ia-service.onrender.com
VITE_API_URL=https://nutriz-backend-service.onrender.com
```
(`wss://` e `https://` em producao, nunca `ws://`/`http://`.)

## 5. Verificar
1. `GET https://nutriz-ia-service.onrender.com/health` -> `{"status":"ok"}`.
2. Login no front -> abrir a EVA logada -> deve responder (sem "sessao
   expirada"). Se der 4001, revise o `JWT_SECRET`.
3. Anonimo na landing -> EVA responde e cita protocolo (RAG ativo).
