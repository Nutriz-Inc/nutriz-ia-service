# Modo Público — Chat anônimo da EVA (Fase 2)

Canal de chat da EVA **sem login**, para visitantes da landing page. Como é
exposto sem autenticação, as proteções abaixo fazem parte da definição de
pronto — não são opcionais.

## Fluxo

```
1. Front chama  POST /session/anonymous     -> recebe { token, session_id, expires_in }
2. Front abre   WS /ws/chat-public?token=... -> valida token anon; frame "conversation"
3. A cada msg:  PII? -> aviso e ignora | jailbreak? -> strike | rate limit? -> encerra
                senão: RAG top-2 -> LLM stream (chunk/done) -> auditoria anônima
```

## Endpoints

### `POST /session/anonymous`
Emite um **session token** temporário (JWT). Sem autenticação prévia.
- Claims: `anon=true`, `session_id` (UUID), `exp` (default 30 min). **Sem `id_user`.**
- Assinado com a mesma `JWT_SECRET`/`HS256` do backend Go.
- Resposta: `{ token, session_id, expires_in }`.

### `WS /ws/chat-public?token=<session_token>`
- Valida o session token anônimo. `anon != true` ou inválido/expirado → close **4001**.
- **Sem consent bloqueante** (não há usuário). O aviso LGPD é exibido no front
  (Fase 3) e o modo público é reforçado no prompt.
- **RAG habilitado, top-2** (economia de tokens de input no free tier do Groq).
- **Sem persistência** de `conversation`/`message`. A conversa vive apenas na
  memória da conexão (memória curta: últimas 10 mensagens). O frame
  `conversation` reutiliza o `session_id`.
- Streaming idêntico ao chat autenticado: frames `conversation` / `chunk` /
  `done` / `error`.
- Prompt adaptado: além da persona padrão, instrui **sugerir cadastro entre a
  3ª e a 5ª mensagem**, de forma natural, sem bloquear.

## Proteções

### 1. Rate limiting (`app/services/rate_limiter.py`)
- Por **IP**: máx **30 mensagens/hora** (janela deslizante).
- Por **sessão**: máx **10 mensagens** (acumulado no tempo de vida da sessão).
- Ao exceder: mensagem amigável sugerindo cadastro + close **4029**.
- **Store in-memory** (dict + `asyncio.Lock`), não `slowapi`. Motivo: `slowapi`
  é desenhado para rotas HTTP (decorator + `Request`), não para o loop de um
  WebSocket, onde cada *mensagem* — não cada conexão — precisa ser contada.
  Para o MVP (container único) isto basta. **Multi-instância exigiria um store
  compartilhado (Redis)** — ponto de evolução conhecido.
- Limites configuráveis via env: `ANON_RATE_LIMIT_PER_IP_HOUR`,
  `ANON_RATE_LIMIT_PER_SESSION`.

### 2. Detecção de PII na entrada (`app/services/public_guard.py`)
- Regex para **CPF** (pontuado ou 11 dígitos), **e-mail** e **telefone** BR.
- Se detectado, o dado sensível **não é repassado ao LLM nem auditado**. A EVA
  responde orientando a não compartilhar dados pessoais e a se cadastrar.
- Protege o visitante e a conformidade LGPD.

### 3. Anti-jailbreak / escopo (`app/services/public_guard.py`)
- Regex para padrões de fuga de escopo ("ignore as instruções", "aja como",
  "system prompt", "modo desenvolvedor", etc.).
- Acumula **strikes** na sessão. Ao atingir **3** (`ANON_MAX_JAILBREAK_STRIKES`),
  encerra a sessão com close **4008**. A tentativa nunca chega ao LLM.

### 4. Auditoria mínima (LGPD)
- `llm_audit` ganhou `is_anonymous BOOLEAN DEFAULT false`,
  `session_id VARCHAR(36) NULL`, `ip_hash VARCHAR(64) NULL`; `user_id` aceita
  NULL para registros anônimos (migration `c9e42f1b83a7`).
- Registro anônimo grava `is_anonymous=true`, `session_id` e `ip_hash`
  (**SHA-256 do IP com sal**, nunca o IP em claro). Sem `user_id`, sem
  `conversation_id`/`message_id`.
- `llm_audit` permanece **append-only e imutável** (regra inviolável).

## Códigos de fechamento do WebSocket público

| Código | Situação                          |
|--------|-----------------------------------|
| 4001   | session token ausente/inválido    |
| 4008   | limite de tentativas de jailbreak |
| 4029   | rate limit (IP ou sessão)         |

No chat **autenticado** (`/ws/chat`) valem ainda: **4001** (token ausente/inválido),
**4002** (`conversation_id` inválido), **4003** (consent LGPD ausente) e **4403**
(papel `adm`/`nurse` sem acesso à EVA — ver `docs/decisoes.md`).

## CORS

O IA service habilita CORS para a origin do Vite (`http://localhost:5173`) via
`CORSMiddleware`, controlado por `CORS_ALLOW_ORIGINS`. O `POST /session/anonymous`
(HTTP) depende disso; conexões WebSocket não passam por preflight CORS.

## Variáveis de ambiente novas

```bash
ANON_SESSION_TTL_MINUTES=30
ANON_RATE_LIMIT_PER_IP_HOUR=30
ANON_RATE_LIMIT_PER_SESSION=10
ANON_MAX_JAILBREAK_STRIKES=3
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

## Testes

- `tests/unit/test_public_guard.py` — PII (CPF/e-mail/telefone) e jailbreak.
- `tests/unit/test_session_service.py` — emissão/validação do token anônimo,
  rejeição de token de nutriz logada, `hash_ip` sem IP em claro.
- `tests/integration/test_ws_chat_public.py` — auth (4001), streaming, prompt
  público com sugestão de cadastro, não-persistência, auditoria anônima, PII,
  rate limit (sessão e IP), jailbreak (3 strikes → 4008).
