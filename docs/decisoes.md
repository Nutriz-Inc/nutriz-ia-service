# Decisões Técnicas

Registro curto de decisões: contexto → decisão → consequência.

## 2026-07-01 — Persistência do turno antes do `done` (não depois)

- **Contexto**: mover a persistência para depois do streaming reduz a latência do 1º token, mas gravar depois do evento `done` cria uma janela em que o cliente desconecta e cancela a gravação de `message`/`llm_audit` (auditoria LGPD obrigatória).
- **Decisão**: persistir após o último chunk e **antes** de enviar `done`.
- **Consequência**: ganho de latência do 1º token preservado (o texto já foi todo entregue quando a persistência roda); cliente que recebeu `done` tem garantia de que tudo foi gravado.

## 2026-07-01 — Threshold de score 0.3 + top-3 + chunks ≤ 300 palavras no RAG

- **Contexto**: top-4 sem threshold injetava chunk irrelevante e inflava o prompt (mais tokens = mais latência no Groq; contexto ruim pode induzir resposta fora do protocolo).
- **Decisão**: descartar chunks com score < 0.3, reduzir para top-3 e truncar cada chunk em 300 palavras na montagem do prompt.
- **Consequência**: ~40% menos tokens de contexto por turno. Se a base de protocolos crescer e as respostas degradarem, recalibrar threshold/top-k medindo com `scripts/bench_ws.py`.

## 2026-07-01 — Provider LLM cacheado com `lru_cache`

- **Contexto**: o provider (e seu client HTTP) era reinstanciado a cada turno, descartando connection pooling e pagando handshake TLS por mensagem (~200ms/turno).
- **Decisão**: `get_llm_provider()` com `lru_cache(maxsize=1)`.
- **Consequência**: client HTTP reutilizado entre turnos e conexões. Testes que trocam `LLM_PROVIDER` precisam chamar `get_llm_provider.cache_clear()`.

## 2026-07-02 — Modelo de embeddings em volume (não baked na imagem)

- **Contexto**: o modelo `paraphrase-multilingual-MiniLM-L12-v2` (~470MB) precisa estar disponível no container. Alternativas: baked na imagem (imagem +470MB, build mais lento, modelo versionado com a imagem) ou baixado no primeiro startup para um volume (imagem enxuta, download 1x por máquina).
- **Decisão**: volume nomeado `models_cache` montado em `/models-cache` (`SENTENCE_TRANSFORMERS_HOME`). O primeiro `docker compose up` baixa o modelo; os seguintes reutilizam o cache.
- **Consequência**: imagem ~1.5GB menor e builds rápidos; o primeiro startup exige internet e demora alguns minutos (healthcheck com `start_period: 300s` acomoda). Para ambientes air-gapped, fazer o bake na imagem em um stage adicional.

## 2026-07-02 — torch CPU-only instalado antes do requirements no Dockerfile

- **Contexto**: em Linux, `pip install sentence-transformers` resolve `torch` com wheels CUDA (vários GB), violando a regra de imagem enxuta.
- **Decisão**: camada dedicada `pip install torch==2.12.0+cpu --index-url https://download.pytorch.org/whl/cpu` antes do `requirements.txt`.
- **Consequência**: imagem CPU-only; ao subir a versão do torch, atualizar o Dockerfile junto.

## 2026-07-02 — Banco de teste dedicado por sessão de teste

- **Contexto**: os testes de integração precisam de Postgres com pgvector real (busca vetorial não funciona em SQLite) sem poluir o banco de desenvolvimento.
- **Decisão**: a suíte cria/destrói `nutriz_ia_test` na mesma instância do compose, com `TRUNCATE` entre testes e `pg_terminate_backend` para derrubar conexões órfãs do TestClient.
- **Consequência**: testes offline e determinísticos; exigem apenas `docker compose up -d db`. CI usa a mesma imagem `pgvector/pgvector:pg16`.

## 2026-07-24 — Bloqueio de `adm`/`nurse` no `/ws/chat` (close 4403)

A EVA atende apenas nutrizes (`common`). O gate existia só no frontend (o FAB
não é montado para staff), mas isso não protege o WebSocket: um token válido de
`adm`/`nurse` conectaria direto em `/ws/chat`.

O router passa a consultar `user.type` logo após a autenticação (antes da
checagem de consent) e recusa perfis de staff com frame `staff_not_allowed` +
close **4403**. Usuário sem linha na tabela espelhada segue permitido — mesma
postura já adotada para o perfil: o chat degrada sem personalização em vez de
bloquear a nutriz, já que em dev o espelho pode não ter o registro.

Custo: uma query a mais por conexão (não por turno), medida como `t_role`.
