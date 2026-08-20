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

---

## 2026-08-19 — Contexto de doação no modo logado, sem nenhum dado clínico

A EVA passou a receber o estado da doação da nutriz (etapa atual, data prevista,
próxima etapa, ponto de coleta, total de doações e volume). O corte foi feito
pelo risco, não pela disponibilidade do dado: **status, datas e local entram;
texto livre não**.

`donation_step.description`, `donation_step_timeline.description`, `job` e
`donation.user_feedback` são preenchidos por adm com teor clínico ("sorologia
reagente", motivo de inaptidão). Em vez de filtrar na saída, as colunas **não
são mapeadas no ORM** e as duas tabelas não são espelhadas — o dado não existe
no processo, então não há como vazar num refactor futuro. Complementarmente, o
status `warn`/`failed` da etapa `Exame de sangue` é mascarado: ele revelaria o
desfecho da sorologia por inferência.

Motivo do rigor: o prompt vai para a Groq (terceiro) e fica gravado no
`llm_audit`, que é append-only e imutável — o que vaza uma vez fica lá.

Custo: ~250 tokens por conexão no system prompt (~+20%), lidos **1x por
conexão** (`t_donations`), não por mensagem.

---

## 2026-08-19 — Id da conversa como valor puro após as leituras que degradam

Bug encontrado ao testar a resiliência do contexto de doação, mas que já existia
no caminho do perfil: quando uma leitura opcional falha, o serviço chama
`db.rollback()` para não deixar a sessão em transação abortada — e o rollback
**expira todos os objetos ORM da sessão**. O `conversation` carregado antes
virava um objeto expirado, e o primeiro acesso a `conversation.id` no turno
seguinte disparava um refresh **síncrono** dentro do loop async:
`MissingGreenlet` → exceção não tratada → WebSocket derrubado.

Ou seja: a degradação que existia para *evitar* a queda da conexão era
exatamente o que a causava. O router agora copia `conv_id = conversation.id`
logo após criar/recuperar a conversa e nunca mais toca no objeto ORM.

Regra geral: depois de um `rollback` de degradação, nenhum objeto ORM carregado
antes dele pode ser usado.
