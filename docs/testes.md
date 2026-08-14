# Testes — nutriz-ia-service

Como rodar a suíte, estrutura e convenções de fixtures/mocks.

## Como rodar

```bash
# Dependências de desenvolvimento
pip install -r requirements-dev.txt

# Banco de teste: precisa do Postgres+pgvector do compose rodando
docker compose up -d db

# Tudo
pytest -v

# Só unitários / só integração
pytest tests/unit -v
pytest tests/integration -v

# Com cobertura (meta: >= 80% em app/services e app/llm)
pytest --cov=app/services --cov=app/llm --cov-report=term-missing
```

Os testes criam (e destroem) um banco dedicado `nutriz_ia_test` na mesma instância
Postgres do compose (mesma imagem `pgvector/pgvector:pg16`). Para apontar para outra
instância, defina `TEST_DATABASE_URL`.

**Todos os testes rodam offline**: nenhum teste chama o Groq real nem baixa o modelo
de embeddings.

## Estrutura

```
tests/
├── conftest.py              # fixtures: banco de teste, seeds, FakeProvider, embeddings fake
├── unit/
│   ├── test_auth.py             # decode JWT: válido, expirado, malformado, sem id_user, leeway
│   ├── test_chat_service.py     # conversas (dono/404/403), histórico, paginação
│   ├── test_consent_service.py  # consent LGPD presente/ausente, versão dos termos
│   ├── test_embeddings.py       # singleton, carga única, encode (modelo mockado)
│   ├── test_eva_prompt.py       # prompts com/sem RAG, com/sem perfil, persona, truncamento
│   ├── test_llm_providers.py    # factory Strategy Pattern + streaming Groq/Ollama mockados
│   ├── test_profile_service.py  # perfil completo/degradado, faixas de idade do bebê
│   └── test_rag_service.py      # score = max(0, 1-distance), ordenação, threshold, top-k
└── integration/
    ├── test_ws_chat.py          # fluxo do WebSocket: auth (4001/4003), chat, multi-turno, reconexão
    ├── test_rest_endpoints.py   # /health, /me, /me/profile, /conversations
    ├── test_persistence.py      # 2 messages por turno, last_message_at, llm_audit completo
    └── test_rag_pipeline.py     # ingest → busca vetorial → chunks; re-ingestão idempotente
```

## Convenções e decisões

- **`FakeProvider`** (`conftest.py`): implementa a interface `LLMProvider` do Strategy
  Pattern e devolve chunks fixos. Registra as mensagens enviadas em `calls` para
  asserções sobre o prompt. Injetado no router via `monkeypatch` de
  `app.routers.chat_ws.get_llm_provider`.
- **Embeddings determinísticos**: fixture autouse troca `encode`/`encode_async`/
  `encode_batch` por uma projeção pseudo-aleatória bag-of-words (semente por palavra
  via crc32). Textos que compartilham palavras produzem vetores próximos — suficiente
  para testar ranking e threshold do RAG sem o modelo real.
- **Banco por sessão, truncamento por teste**: o banco `nutriz_ia_test` é dropado e
  recriado no início da sessão (`Base.metadata.create_all` + `CREATE EXTENSION vector`).
  Após cada teste que usa `db_session`, todas as tabelas são truncadas. Antes do
  truncate, conexões órfãs são derrubadas (`pg_terminate_backend`) — a sessão do
  WebSocket cancelada pelo `TestClient` pode ficar "idle in transaction" e travar o
  `TRUNCATE`.
- **Um único event loop de sessão** (`pytest.ini`): fixtures e testes async compartilham
  o mesmo loop. Misturar loops deixa conexões asyncpg presas (deadlock). O engine de
  teste usa `NullPool` para conviver com o loop interno do `TestClient` (WebSocket).
- **JWT de teste**: `make_token()` no conftest, com `JWT_SECRET` fixo de teste definido
  em variável de ambiente antes do import do app.
- **Provider cacheado**: `get_llm_provider` usa `lru_cache`; testes que trocam
  `LLM_PROVIDER` devem chamar `get_llm_provider.cache_clear()`.
- **Modos futuros da EVA** (`/ws/chat-public`, copiloto admin) **não têm testes**:
  ainda não existem no código. Criar os testes junto com a implementação (Sprints 8-9).

## Regressões cobertas

- **Múltiplos turnos na mesma conexão WebSocket** (`test_multiplos_turnos_na_mesma_conexao`):
  2ª e 3ª mensagens funcionam na mesma conexão.
- **JSON inválido não derruba a conexão** (`test_json_invalido_nao_derruba_conexao`).
- **Persistência garantida antes do `done`** (`test_turno_grava_duas_mensagens_e_um_audit`):
  cliente que desconecta após o `done` não perde `message`/`llm_audit`.
