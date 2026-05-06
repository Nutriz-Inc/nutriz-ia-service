# Nutriz IA Service

Microsserviço de inteligência artificial da plataforma Nutriz, parceria com Lactare/Eurofarma.
Responsável pelo chatbot **EVA**, que atende nutrizes doadoras de leite materno.

##  Documentação

- [`docs/perguntas-teste.md`](./docs/perguntas-teste.md) — perguntas reais para validar o RAG

##  Stack

- Python 3.11+ · FastAPI · WebSocket
- PostgreSQL 16 + pgvector
- Groq (Llama 3.3 70B) · OpenRouter · Ollama
- sentence-transformers (embeddings locais)

##  Setup

> Em desenvolvimento. Documentação completa de setup chegará na próxima sprint.

##  Convenção de branches

- `main` — versão estável (produção)
- `develop` — integração de features
- `feat/<nome>` — novas funcionalidades
- `fix/<nome>` — correções
- `chore/<nome>` — configurações, dependências
- `docs/<nome>` — documentação

PRs são abertos sempre contra `develop`.