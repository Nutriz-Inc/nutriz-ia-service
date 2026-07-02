# Performance — Latência do Chat da EVA

Registro do baseline de latência, das otimizações aplicadas e dos ganhos medidos.

## Como medir

1. Suba o banco e o servidor (`docker compose up -d` + `uvicorn app.main:app --port 8000`).
2. Rode o benchmark cliente: `python -m scripts.bench_ws --turns 6`
   - Mede a latência percebida pela nutriz: tempo do envio até o primeiro chunk (TTFT) e tempo total do turno.
   - Requer o usuário seed com consent no banco (ver README).
3. Os logs `[latency]` do servidor trazem a quebra por fase de cada turno:
   `t_auth`, `t_consent`, `t_conversation`, `t_profile` (setup da conexão) e
   `t_history_e_embedding`, `t_rag_sql`, `t_llm_first_token`, `t_llm_total`,
   `t_persist_*` (por turno).
4. `llm_audit.latency_ms` continua registrando o tempo total de streaming de cada chamada (baseline histórico).

## Metas

- Primeiro token do streaming em **< 2s** (após warm-up)
- Overhead do pipeline (auth + perfil + RAG + persistência) em **< 500ms** por turno

## Baseline (medido em 2026-07-01, antes das otimizações)

Histórico `llm_audit.latency_ms` (streaming total, 8 registros): média 1671ms, p50 1740ms, max 2141ms.

Benchmark de 6 turnos na mesma conexão (Groq `llama-3.3-70b-versatile`):

| Turno | t_embedding | t_rag_sql | t_llm_first_token | TTFT cliente | Total |
|---|---|---|---|---|---|
| 1 (cold) | **5411ms** | 45ms | 739ms | **6741ms** | 7875ms |
| 2 | 57ms | 24ms | 341ms | 845ms | 1987ms |
| 3 | 42ms | 5ms | 333ms | 841ms | 1880ms |
| 4 | 136ms | 5ms | 782ms | 1459ms | 2066ms |
| 5 | 146ms | 47ms | 325ms | 1023ms | 2415ms |
| 6 | 55ms | 3ms | **16913ms** ⚠ | 17460ms | 18227ms |

Setup da conexão: `t_auth=0ms | t_consent=184ms | t_conversation=25ms | t_profile=18ms` (228ms).

Diagnóstico:

1. **Cold start do modelo de embeddings (5,4s)** — o sentence-transformers carregava lazy na primeira mensagem. Maior gargalo.
2. **Provider LLM reinstanciado a cada turno** — novo `AsyncGroq`/client HTTP por mensagem (gap de ~400ms entre `t_llm_first_token` do servidor e o TTFT do cliente).
3. **Persistência da mensagem da usuária no caminho crítico** — commit antes de chamar o LLM.
4. **I/O sequencial** — histórico e embedding rodavam em série.
5. **Turno 6 (16,9s)**: rate limit do free tier do Groq (TPM) com retry interno do SDK. Não é gargalo de código — limitação conhecida do free tier; não há mitigação sem violar custo zero.

## Otimizações aplicadas e ganhos medidos

| Otimização | Commit | Efeito medido |
|---|---|---|
| Pré-aquecer embeddings no lifespan do FastAPI | `perf: pre-aquece modelo de embeddings no startup` | TTFT da 1ª mensagem: 6741ms → 1454ms (**−78%**). Warm-up de ~4,6s pago no startup, invisível para a nutriz |
| Reutilizar instância do provider LLM (lru_cache) e client HTTP | `perf: reutiliza instancia do provider llm entre turnos` | Gap cliente/servidor por turno: ~400ms → ~220ms |
| Paralelizar encode do embedding (thread) com busca de histórico (banco) | `perf: paraleliza encode do embedding com busca de historico` | Fases somadas (~60–190ms) → executam juntas (50–174ms no pior caso) |
| Persistência do turno após o streaming | `perf: move persistencia do turno para depois do streaming` | ~10–35ms fora do caminho do 1º token; auditoria intacta |
| Threshold de score 0.3 + top-3 + chunks ≤300 palavras | `perf: aplica threshold de score, top-3 e limite de palavras no rag` | ~40% menos tokens de contexto RAG no prompt |
| Pool asyncpg (`pool_size=10`, `max_overflow=20`, `pool_pre_ping`) | `perf: configura pool de conexoes do engine asyncpg` | Robustez em conexões WS longas; evita erro de conexão morta |

## Resultado (medido em 2026-07-01, após as otimizações)

| Turno | t_history_e_embedding | t_rag_sql | t_llm_first_token | TTFT cliente | Total |
|---|---|---|---|---|---|
| 1 | 50ms | 51ms | 881ms | **1454ms** | 2246ms |
| 2 | 116ms | 4ms | 281ms | 617ms | 1764ms |
| 3 | 174ms | 5ms | 319ms | 698ms | 1874ms |
| 4 | 61ms | 4ms | 637ms | 775ms | 1860ms |
| 5 | 105ms | 4ms | 380ms | 551ms | 1945ms |
| 6 | 64ms | 4ms | 1471ms | 1572ms | 2699ms |

### Comparativo

| Métrica | Baseline | Otimizado | Ganho |
|---|---|---|---|
| TTFT 1ª mensagem (cold) | 6741ms | 1454ms | **−78%** |
| TTFT turnos quentes (mediana) | 934ms | 658ms | −30% |
| Overhead do pipeline antes do 1º token | 84–217ms (+5,4s no cold) | 54–179ms | meta <500ms atingida |
| Meta 1º token < 2s | violada na 1ª msg | todos os turnos < 2s | atingida |

O que domina a latência agora é o próprio Groq (`t_llm_first_token` 281–1471ms, variação do free tier).

## O que NÃO foi feito (por decisão)

- Trocar o modelo LLM por um menor (qualidade em saúde vem primeiro).
- Cache de respostas do LLM (respostas são personalizadas por perfil/contexto).
- Remover ou adiar o registro em `llm_audit` (obrigatório; apenas movido para depois do streaming).
