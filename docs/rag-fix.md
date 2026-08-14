# Laudo — Correção do RAG (Fase 1)

## Sintoma

A EVA respondia sem usar os documentos ingeridos. A base tinha chunks, mas as
respostas nunca citavam dados específicos dos protocolos — o RAG estava sendo
efetivamente contornado.

## Diagnóstico

Auditoria conduzida na ordem ingestão → recuperação → prompt → evidência E2E.

### Ingestão/indexação (OK)
- `SELECT count(*), source FROM kb_chunks GROUP BY source` → 13 chunks
  (5 + 8) em dois protocolos. Ingestão rodou.
- `SELECT count(*) FROM kb_chunks WHERE embedding IS NULL` → 0. Embeddings
  preenchidos, dimensão `vector(384)` correta.
- Índice presente: `ix_kb_chunks_embedding` — porém **ivfflat** com `lists=100`.

### Recuperação (CAUSA RAIZ AQUI)
Comparação da mesma query com e sem uso do índice, no banco de produção:

```
Query: "Como devo armazenar o leite materno ordenhado?"

COM índice ivfflat (probes=1, default):
  doadoras_triagem...  distance=0.8314  score=0.1686   <- único resultado

SEM índice (seq scan, ground truth):
  ordenha_leite_humano distance=0.3332  score=0.6668
  doadoras_triagem...  distance=0.3952  score=0.6048
  doadoras_triagem...  distance=0.4225  score=0.5775
  ...
```

O índice retornava **1 resultado errado com score 0.17**, abaixo do
`MIN_SCORE_THRESHOLD = 0.3`. Resultado: `search_chunks` devolvia lista vazia
em praticamente toda pergunta, e a EVA caía sempre no modo "sem contexto".

**Por quê:** o índice `ivfflat` foi criado na migration inicial
(`ea59d6d81ae9`) sobre a tabela **vazia**. O `ivfflat` particiona o espaço em
`lists` clusters usando os dados presentes **no momento da criação**. Criado
sobre zero linhas, os centroides ficam degenerados. Com o default
`ivfflat.probes = 1`, cada busca varre apenas 1 das 100 listas — recall
próximo de zero. Os poucos vizinhos que retornavam eram quase aleatórios,
com score baixo, descartados pelo threshold.

O `rag_service.search_chunks` estava **correto**: distância cosseno via
`cosine_distance` / `<=>`, `score = max(0, 1 - distance)`, ordenação e
threshold adequados. O bug era 100% no índice.

### Uso no prompt (OK)
`chat_ws → search_chunks() → build_messages_for_llm_with_rag()` injeta os
chunks no `system`. Sem caminho curto-circuitando o RAG. O problema era só
que `search_chunks` retornava `[]` por causa do índice.

### Por que os testes não pegaram
O banco de teste é criado via `Base.metadata.create_all` a partir dos models,
e o model `KbChunk` **não declarava o índice vetorial**. Logo os testes
rodavam com seq scan (recall perfeito) e nunca exercitavam o ivfflat
degenerado da produção. Divergência teste/prod mascarou o bug.

## Causa raiz

Índice `ivfflat (lists=100)` criado sobre tabela vazia → centroides
degenerados → com `probes=1`, recall ~0 → `search_chunks` retorna vazio ou
lixo abaixo do threshold → EVA sempre sem contexto documental.

## Correção

1. **Migration `b7c31a9f02d4`**: troca `ivfflat` por **`hnsw`
   (`m=16, ef_construction=64`, `vector_cosine_ops`)**. HNSW constrói o grafo
   incrementalmente a cada insert, funcionando corretamente mesmo criado antes
   da ingestão e adequado a bases pequenas.
2. **Model `KbChunk`**: índice HNSW declarado em `__table_args__` para que o
   banco de teste use a **mesma** estrutura de busca da produção, fechando a
   divergência que escondeu o bug.

## Como foi validado

- **Migration aplicada** no container: `\d kb_chunks` confirma
  `ix_kb_chunks_embedding hnsw (embedding vector_cosine_ops)`.
- **Busca real** (`search_chunks`) pós-fix, sem tocar no threshold:
  ```
  Q: Como devo armazenar o leite materno ordenhado?
    ordenha_leite_humano  score=0.6668
    doadoras_triagem...   score=0.6048
    doadoras_triagem...   score=0.5775
  ```
- **Prova ponta a ponta** via WebSocket com Groq real. Fato que só existe no
  protocolo (`ordenha_leite_humano.md`: "o tempo de validade será contado a
  partir da data/hora da primeira ordenha"):
  > **Pergunta:** "A partir de que momento eu conto o tempo de validade do
  > leite congelado em casa?"
  > **EVA:** "O tempo de validade do leite congelado em casa é contado a
  > partir da data e hora da primeira ordenha, e não do momento em que o leite
  > foi congelado. (...)"
- **Testes** (`pytest -v`, 87 verdes), incluindo:
  - `test_indice_de_busca_e_hnsw`: banco de teste usa hnsw (paridade).
  - `test_chunk_relevante_sempre_entra_no_prompt`: anti-bypass — havendo
    chunk correspondente, ele SEMPRE entra no prompt do LLM.
  - `test_sem_documento_correspondente_prompt_sem_contexto`: sem match, EVA vai
    a conhecimento geral, sem seção de contexto e sem dizer "não sei".

## Como reexecutar a ingestão (reprodutível)

```bash
docker compose up -d
docker exec nutriz-ia-app alembic upgrade head     # aplica índice hnsw
docker exec nutriz-ia-app python -m scripts.ingest_protocols
```

A ingestão é idempotente por `source` (re-ingerir apaga os chunks anteriores
do arquivo antes de reinserir).
