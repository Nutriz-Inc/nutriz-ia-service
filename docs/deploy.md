# Deploy do nutriz-ia-service no Render (free tier)

Serviço FastAPI da EVA em container Docker, no Render free (512 MB de RAM). O
modelo de embeddings cabe no limite via poda de vocabulário (ver
[otimizacao-memoria.md](otimizacao-memoria.md)): repouso ~312 MiB, pico ~336 MiB.

Ordem: **1)** publicar o artefato → **2)** preparar o banco → **3)** deploy no
Render → **4)** ingestão → **5)** verificação.

---

## 1. Artefato de embeddings (GitHub Release privado + PAT)

O `model.onnx` (~156 MB) **não vai no Git** (limite de 100 MB/arquivo; está no
`.gitignore`). O Dockerfile o baixa de um **GitHub Release deste repositório
privado** via **API de assets autenticada**, e confere o **SHA-256**. O
`model.onnx` e o `tokenizer.json` são um **par**: se descasarem, os IDs viram
lixo silencioso — publique/regenere sempre os dois juntos, sob a mesma tag.

Como o repositório é privado (decisão do time — parceria Eurofarma, domínio de
saúde), o download exige um token. Ele entra como **build secret** (mount),
**nunca** como `ARG`: não fica em layer, no histórico da imagem nem no log.

### Tag e hashes atuais

- Tag do release: **`embeddings-v1`**
- `model.onnx`     — SHA-256 `8bbc8d80fe3f829db1160f201049825311201ddfbddf22a143efe0908b2eb0a8`
- `tokenizer.json` — SHA-256 `ab94abc7b08e3b3a41c90708e96336a0523cb4cd2ebd5fe37be32729d15b8756`

Esses hashes são o default dos `ARG MODEL_SHA256`/`TOKENIZER_SHA256` no Dockerfile.

### PAT de leitura (fine-grained)

Gerar em **GitHub → Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token**:

- **Resource owner:** `Nutriz-Inc`
- **Repository access:** *Only select repositories* → `nutriz-ia-service` (só este)
- **Permissions → Repository → Contents: Read-only** (nada além disso)
- **Expiration:** 90 dias (recomendado)

Escopo mínimo: só lê o conteúdo/os assets deste repo, não escreve nada.

**Nunca** cole o token em commit, log ou arquivo versionado. Onde usar:

- **Local (validar o build):** salve o token num arquivo **fora do repo** (ou use
  o `.gitignore`, que já cobre `gh_token*.txt`) e rode:
  ```bash
  DOCKER_BUILDKIT=1 docker build --secret id=gh_token,src=./gh_token.txt -t nutriz-ia-service:local .
  ```
- **Render:** cadastre um **Secret File** chamado `gh_token` com o token como
  conteúdo (Dashboard → serviço → *Environment* → *Secret Files*). O BuildKit o
  monta no build via `id=gh_token`. Não é uma env var — é Secret File.

**Rotação:** antes de expirar, gere um novo fine-grained token com o mesmo
escopo, atualize o Secret File `gh_token` no Render (e o arquivo local), redeploy
e **revogue o antigo**. Nenhuma mudança de código é necessária.

### Publicar / republicar o release

Com o par já gerado em `models/` (ver "Regenerar" abaixo):

```bash
gh release create embeddings-v1 \
  models/model.onnx models/tokenizer.json \
  --repo Nutriz-Inc/nutriz-ia-service \
  --title "Embeddings podados v1" \
  --notes "paraphrase-multilingual-MiniLM-L12-v2, vocab podado 250k->50k (fp32 ONNX)."
```

> Se regerar o artefato, use uma **tag nova** (`embeddings-v2`, ...), **não**
> reaproveite a tag com conteúdo diferente. Ao trocar a tag, atualize no
> Dockerfile: `ARG EMBEDDINGS_RELEASE` e os dois `ARG *_SHA256` (e os hashes
> nesta seção). O `curl` casa o `Accept: application/octet-stream` na API de
> assets; o `sha256sum -c` no build falha (e derruba o build) se o par não bater.

### Regenerar o par (fora do build do Docker)

```bash
python scripts/export_model.py build              # fp32 ONNX + tokenizer (usa torch)
python scripts/prune_vocab.py build models 50000  # poda -> models/model.onnx + tokenizer.json
sha256sum models/model.onnx models/tokenizer.json # copiar os novos hashes para o Dockerfile e este doc
```

---

## 2. Banco de dados (produção)

As 4 tabelas do IA service (`conversations`, `messages`, `kb_chunks`,
`llm_audit`) são criadas **manualmente** por quem administra o banco, rodando
[`migracao-neon.sql`](migracao-neon.sql). Esse script:

- cria as tabelas no estado **HEAD do Alembic (`d4e91a7c22b0`)**, com índice
  **HNSW** (nunca ivfflat) e `llm_audit` sem FK física;
- **carimba** a `alembic_version` com a head — por isso o serviço sobe com
  `RUN_MIGRATIONS=false` e não mexe no schema.

⚠️ `conversations` tem FK para `"user"(id_user)` do backend Go: rode o SQL **só
depois** que as tabelas do Go existirem no banco. Requer as extensões `vector` e
`pgcrypto`.

---

## 3. Deploy no Render

Via blueprint [`render.yaml`](../render.yaml) (Docker, plano free,
`healthCheckPath: /health`). Conecte o repositório no Render e aponte para o
blueprint, ou crie um "Web Service" Docker manualmente com as mesmas variáveis.

### Variáveis de ambiente a colar no painel (as `sync: false`)

| Variável | O que é |
|---|---|
| `DATABASE_URL` | URL do Postgres de produção. Aceita `postgres://`/`postgresql://` (o app normaliza para asyncpg). |
| `JWT_SECRET` | **Idêntica** à `AUTH_JWT_SECRET` do backend Go. |
| `GROQ_API_KEY` | Chave do console.groq.com. |
| `OPENROUTER_API_KEY` | Opcional — fallback quando a Groq retorna 429. |
| `CORS_ALLOW_ORIGINS` | Origem(ns) do front. Confirmado: `https://web-nutriz.vercel.app` (lista separada por vírgula). |

As demais (`LLM_PROVIDER`, `GROQ_MODEL`, `EMBEDDINGS_MODEL_DIR`,
`RUN_MIGRATIONS=false`, `RUN_INGESTION=false`, `APP_ENV`, `LOG_LEVEL`, limites do
modo público) já vêm fixas no `render.yaml`.

### Secret File do build (obrigatório)

Além das env vars, cadastre um **Secret File** chamado **`gh_token`** com o PAT
fine-grained (seção 1) como conteúdo. É o que autentica o download do artefato no
build. Sem ele, o build falha ao baixar o `model.onnx`.

> O build baixa o artefato do Release privado (passo 1) — a tag `embeddings-v1`
> precisa existir e o Secret File `gh_token` estar cadastrado antes do 1º deploy.

---

## 4. Ingestão dos protocolos (one-off)

O boot **não** ingere (`RUN_INGESTION=false`). Rode a carga uma vez após o banco
estar pronto, por um destes caminhos:

- **Render Shell** (aba Shell do serviço): `python -m scripts.ingest_protocols`
- ou um deploy pontual com `RUN_INGESTION=true` e depois volte para `false`.

A ingestão é idempotente (apaga+reinsere por fonte). Confirme com
`SELECT count(*) FROM kb_chunks;` (deve ser > 0).

---

## 5. Verificação pós-deploy

1. `GET https://<servico>.onrender.com/health` → `{"status":"ok"}`.
2. `POST /session/anonymous` retorna um token.
3. WebSocket `/ws/chat-public?token=<token>`: enviar uma pergunta cuja resposta
   está nos protocolos e conferir que a EVA responde ancorada no conteúdo (ver o
   e2e do "1 cm" em [otimizacao-memoria.md](otimizacao-memoria.md)).

---

## Flags de boot (entrypoint)

| Var | Default | Local (compose) | Render |
|---|---|---|---|
| `RUN_MIGRATIONS` | `true` | `true` (cria tabelas no banco efêmero) | `false` (schema manual) |
| `RUN_INGESTION` | `false` | `true` (ingere protocolos) | `false` (one-off) |

O servidor sobe com `--proxy-headers --forwarded-allow-ips="*"` para respeitar o
`X-Forwarded-For` atrás do proxy do Render (IP real usado no rate limit e no
`ip_hash` do modo público).
