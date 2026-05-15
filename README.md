# Nutriz IA Service

Microsserviço de inteligência artificial da plataforma **Nutriz**, em parceria com **Lactare/Eurofarma**. Responsável pelo chatbot **EVA**, que atende nutrizes doadoras de leite materno 24/7 via WebSocket, com respostas personalizadas baseadas em RAG (Retrieval Augmented Generation) sobre protocolos da Rede Brasileira de Bancos de Leite Humano (rBLH/Fiocruz).

---

## 🤱 Sobre a EVA

A EVA é uma assistente virtual especializada em:

- **Doação de leite materno**: elegibilidade, processo, logística, armazenamento
- **Amamentação**: técnica, ordenha, dúvidas comuns
- **Acolhimento**: orientação humanizada, sem infantilização

**Conhecimento baseado em fontes verificadas** (protocolos rBLH/Fiocruz/Lactare) ingestados como base vetorial. Para perguntas fora do conhecimento documental, recorre a conhecimento geral confiável (MS, OMS, SBP, Fiocruz) com transparência sobre a limitação.

**Personalização**: a EVA consulta o perfil consolidado da nutriz (idade do bebê, localização) a cada conversa para adaptar as respostas — sem expor dados sensíveis de saúde.

**Limites inegociáveis**:
- Não prescreve medicamentos, dosagens ou tratamentos
- Não substitui avaliação médica, de enfermagem ou de nutricionista
- Encaminha emergências (SAMU 192) e casos clínicos específicos à equipe Lactare

---

## 🏗️ Arquitetura

```
┌───────────────────┐
│  nutriz-web       │  ← React (interface da nutriz - em desenvolvimento)
└─────────┬─────────┘
          │
          ├──────────────► nutriz-backend (Go/FluxGo) :3333
          │                    │
          │                    │ (user, baby, address, donations, consent_log)
          │                    │
          └──────────────► nutriz-ia-service (FastAPI) :8000  ◄─── ESTE REPO
                               │
                               ▼
                     PostgreSQL 16 + pgvector :5433
```

O `nutriz-ia-service` é **autônomo**. Usa JWT compartilhado com o backend Go para autenticação, mas opera de forma independente. As tabelas do backend Go (`user`, `user_baby`, `address`, `consent_log`) são acessadas **apenas em modo read-only**.

---

## 🛠️ Stack

| Camada | Tecnologia | Versão |
|---|---|---|
| Linguagem | Python | 3.13+ |
| Framework | FastAPI + WebSocket nativo | 0.115.6 |
| ORM | SQLAlchemy 2.0 async + Alembic | 2.0.36 |
| Driver | asyncpg | 0.30.0 |
| Banco | PostgreSQL + pgvector | 16 / 0.3.6 |
| LLM primário | Groq (Llama 3.3 70B) | groq SDK 0.15.0 |
| LLM fallback dev | Ollama (Llama 3.2 3B) | via HTTP |
| Embeddings | sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`, 384d) | 3.3.1 |
| Auth | PyJWT (HS256, compartilhado com backend Go) | 2.10.1 |
| Containerização | Docker + Docker Compose | — |

---

## ✅ Pré-requisitos

- **Python 3.13** ou superior
- **Docker** + **Docker Compose**
- **Conta gratuita no Groq** ([console.groq.com](https://console.groq.com)) para chave de API
- **~1.5 GB livres em disco** (PyTorch CPU + modelo de embeddings + container Postgres)

---

## 🚀 Setup

### 1. Clonar o projeto

```bash
git clone https://github.com/Nutriz-Inc/nutriz-ia-service.git
cd nutriz-ia-service
```

### 2. Criar ambiente virtual

```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Linux/Mac
python -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependências

> ⚠️ **Instale o PyTorch CPU-only PRIMEIRO** para evitar baixar a versão com CUDA (~2 GB).

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

Crie o arquivo `.env` na raiz do projeto (não commitado):

```env
# Banco de dados
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/nutriz_ia

# JWT compartilhado com backend Go
JWT_SECRET=<mesmo_secret_do_backend_go>
JWT_ALGORITHM=HS256

# LLM
LLM_PROVIDER=groq
GROQ_API_KEY=<sua_chave_groq>
GROQ_MODEL=llama-3.3-70b-versatile
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

# Embeddings
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

# Ambiente
APP_ENV=development
LOG_LEVEL=INFO
```

### 5. Subir o banco de dados

```bash
docker compose up -d
docker ps  # confere se nutriz-ia-db está healthy
```

### 6. Aplicar migrations

```bash
alembic upgrade head
```

### 7. Ingerir protocolos no banco vetorial

Os protocolos da rBLH/Fiocruz/Lactare estão em `docs/protocolos/` como arquivos Markdown. Para ingerir (gera embeddings e popula `kb_chunks`):

```bash
python -m scripts.ingest_protocols
```

> ⚠️ **Primeira execução**: o script baixa o modelo de embeddings da Hugging Face (~470 MB). Faz uma vez só — fica cacheado em `~/.cache/huggingface/`.

### 8. Iniciar o servidor

```bash
uvicorn app.main:app --reload --port 8000
```

A API estará disponível em `http://localhost:8000`.

---

## 📡 Endpoints

### REST

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| `GET` | `/health` | Health check | — |
| `GET` | `/me/profile` | Perfil consolidado da nutriz + status de consentimento LGPD | JWT |
| `GET` | `/conversations` | Lista conversas da nutriz (paginação `?page=1&page_size=20`) | JWT |
| `GET` | `/conversations/{id}/messages` | Mensagens de uma conversa | JWT |

### WebSocket

| Rota | Descrição | Auth |
|---|---|---|
| `/ws/chat?token=<jwt>` | Chat com a EVA (streaming token-a-token) | JWT via query string |
| `/ws/chat?token=<jwt>&conversation_id=<uuid>` | Continuar conversa existente | JWT via query string |

**Bloqueio LGPD**: se a nutriz não tiver registro em `consent_log`, o WebSocket fecha com código `4003` e mensagem estruturada `{"type": "error", "code": "lgpd_consent_required"}`.

---

## 📁 Estrutura de pastas

```
nutriz-ia-service/
├── app/
│   ├── main.py                      # Entry point FastAPI
│   ├── config.py                    # Pydantic Settings (lê .env)
│   ├── database.py                  # SQLAlchemy async engine + sessão
│   ├── models/                      # ORM models
│   │   ├── user.py                  # ↓ read-only (espelhadas do Go)
│   │   ├── user_baby.py
│   │   ├── address.py
│   │   ├── consent_log.py
│   │   ├── conversation.py          # ↓ próprias do IA service
│   │   ├── message.py
│   │   ├── kb_chunk.py
│   │   └── llm_audit.py
│   ├── schemas/                     # Schemas Pydantic
│   │   ├── conversation.py
│   │   ├── profile.py
│   │   └── rag.py
│   ├── routers/                     # Endpoints REST/WebSocket
│   │   ├── health.py
│   │   ├── me.py
│   │   ├── chat_ws.py
│   │   └── conversations.py
│   ├── services/                    # Lógica de negócio
│   │   ├── auth.py
│   │   ├── auth_ws.py
│   │   ├── chat_service.py
│   │   ├── rag_service.py
│   │   ├── embeddings.py
│   │   ├── profile_service.py
│   │   ├── consent_service.py
│   │   └── eva_prompt.py
│   └── llm/                         # Strategy Pattern de providers
│       ├── provider.py              # Abstract base
│       ├── groq_provider.py
│       └── ollama_provider.py
├── docs/
│   ├── protocolos/                  # Markdowns ingestados pelo RAG
│   │   ├── doadoras_triagem_selecao_acompanhamento.md
│   │   └── ordenha_leite_humano.md
│   └── perguntas-teste.md           # Bateria de testes do RAG
├── migrations/                      # Alembic
│   └── versions/
├── scripts/
│   └── ingest_protocols.py          # Script de ingestão de .md
├── docker-compose.yml
├── requirements.txt
└── alembic.ini
```

---

## 🔐 Variáveis de ambiente

| Variável | Descrição | Default |
|---|---|---|
| `DATABASE_URL` | URL de conexão PostgreSQL (async) | — (obrigatório) |
| `JWT_SECRET` | Secret compartilhado com backend Go | — (obrigatório) |
| `JWT_ALGORITHM` | Algoritmo JWT | `HS256` |
| `LLM_PROVIDER` | Provider ativo | `groq` |
| `GROQ_API_KEY` | Chave da API Groq | — (obrigatório se `LLM_PROVIDER=groq`) |
| `GROQ_MODEL` | Modelo Groq | `llama-3.3-70b-versatile` |
| `OPENROUTER_API_KEY` | Chave OpenRouter (alternativa futura) | `""` |
| `OLLAMA_BASE_URL` | URL do Ollama local | `http://localhost:11434` |
| `OLLAMA_MODEL` | Modelo Ollama | `llama3.2:3b` |
| `EMBEDDING_MODEL` | Modelo sentence-transformers | `paraphrase-multilingual-MiniLM-L12-v2` |
| `APP_ENV` | Ambiente | `development` |
| `LOG_LEVEL` | Nível de log | `INFO` |

---

## 🧪 Testando localmente

### Gerar um token JWT manualmente

```python
import jwt
from datetime import datetime, timedelta, timezone
from app.config import settings

token = jwt.encode(
    {
        "id_user": "<uuid_do_user_cadastrado_no_banco>",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp()),
    },
    settings.JWT_SECRET,
    algorithm=settings.JWT_ALGORITHM,
)
print(token)
```

### Testar endpoint REST

```bash
curl -X GET "http://localhost:8000/me/profile" \
  -H "Authorization: Bearer <token>"
```

### Testar WebSocket

```python
import asyncio, json, websockets

async def chat():
    uri = "ws://localhost:8000/ws/chat?token=<token>"
    async with websockets.connect(uri) as ws:
        print(await ws.recv())  # {"type": "conversation", ...}
        await ws.send(json.dumps({"message": "posso doar leite?"}))
        while True:
            msg = json.loads(await ws.recv())
            if msg["type"] == "chunk":
                print(msg["content"], end="", flush=True)
            elif msg["type"] == "done":
                break

asyncio.run(chat())
```

---

## 🧠 Decisões arquiteturais

- **Banco compartilhado em produção, separado em dev**: o IA service e o backend Go terão o mesmo banco em produção. Em dev, isolamento por simplicidade.
- **Tabelas espelhadas do Go são read-only**: `user`, `user_baby`, `address`, `consent_log` são mantidas pelo backend Go.
- **JWT compartilhado**: payload `{id_user, exp}` + `HS256` + clockSkew de 30s. Mesmo secret nos dois serviços.
- **`llm_audit` sem FK física**: preserva auditoria LGPD após exclusão de usuário (direito ao esquecimento).
- **Strategy Pattern para LLM**: trocar Groq por OpenAI/Anthropic/Ollama sem reescrever lógica de chat.
- **Embeddings locais**: zero custo de API, suporte a português, ~470 MB de modelo + ~250 MB de PyTorch CPU.
- **Singleton no `EmbeddingsService`**: modelo carrega 1x na memória e fica em cache durante o processo.
- **RAG com cosine distance**: alinhado com índice IVFFLAT do pgvector (`vector_cosine_ops`).
- **Perfil capturado uma vez por sessão WebSocket**: sem cache cross-session; mudanças refletem na próxima conexão.
- **Close code 4003 reservado para LGPD** (`4001` para auth).

---

## 🌿 Convenção de branches

- `main` — versão estável (produção)
- `develop` — integração de features
- `feat/<nome>` — novas funcionalidades
- `fix/<nome>` — correções
- `chore/<nome>` — configurações, dependências
- `docs/<nome>` — documentação

PRs são abertos sempre contra `develop`. Commits seguem [Conventional Commits](https://www.conventionalcommits.org/) em português, com mensagens descritivas no corpo.

---

## 🗺️ Roadmap

### ✅ Concluído

- **Sprint 1**: Setup técnico (Docker, FastAPI, Alembic)
- **Sprint 2**: Modelos ORM + migrations alinhadas com backend Go
- **Sprint 3**: WebSocket de chat com streaming via Groq + auditoria LGPD
- **Sprint 4**: Sistema RAG completo (sentence-transformers + busca semântica + refinamento de prompts)
- **Sprint 5**: Personalização por perfil consolidado + bloqueio LGPD

### 📋 Em planejamento

- **Sprint 6**: Refinamentos do RAG (threshold de score, mais protocolos `.md`, avaliação automatizada)
- Integração com WhatsApp via webhook
- Sistema de feedback da nutriz (👍/👎 nas respostas)
- Métricas de qualidade do RAG
- Testes automatizados (unit + integração)
- Captura de tokens consumidos (`tokens_input`/`tokens_output`)

---

## 📖 Documentação adicional

- [`docs/perguntas-teste.md`](./docs/perguntas-teste.md) — Bateria de perguntas reais para validação do RAG
- [`docs/protocolos/`](./docs/protocolos/) — Protocolos da rBLH/Fiocruz em Markdown

---

## 📝 Licença

Projeto acadêmico — Challenge FIAP 2026 em parceria com Eurofarma/Lactare.
