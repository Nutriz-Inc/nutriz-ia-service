-- ============================================================================
-- Migracao manual do nutriz-ia-service para o banco de producao (Neon)
-- Estado: HEAD do Alembic = d4e91a7c22b0
--
-- Gerado A PARTIR DAS MIGRATIONS REAIS deste servico (nao do SQL antigo).
-- Reproduz exatamente o schema que `alembic upgrade head` produziria, para o
-- Leo rodar a mao. Ao final, carimba a alembic_version com a head correta, de
-- modo que o servico NAO tente rodar as migrations de novo.
--
-- Idempotente (IF NOT EXISTS em tudo) e transacional (BEGIN/COMMIT): rodar
-- novamente nao causa erro nem duplica.
--
-- ----------------------------------------------------------------------------
-- ATENCAO / DEPENDENCIA (LER ANTES DE RODAR):
--
-- A tabela `conversations` tem uma FK FISICA para "user"(id_user), que pertence
-- ao backend Go. Se a tabela "user" do Go NAO existir neste banco, o CREATE
-- TABLE conversations FALHA. Rode este script APENAS no banco que ja tem as
-- tabelas do Go (user, user_baby, address, consent_log). Ordem correta em
-- producao: migrations do Go primeiro, este script depois.
--
-- ----------------------------------------------------------------------------
-- DIVERGENCIAS em relacao a descricao passada (o schema real venceu):
--
--  * Nomes das tabelas sao PLURAL: conversations, messages, kb_chunks,
--    llm_audit. NAO sao singular. (As migrations sempre usaram plural.)
--  * NAO existe enum `enum_message_role`. A coluna messages.role e VARCHAR(20).
--    Nenhum tipo enum e criado no schema.
--  * As colunas de referencia em llm_audit chamam-se user_id / conversation_id
--    / message_id (NAO id_user / id_conversation / id_message). Todas nullable
--    para registros anonimos, conforme pedido.
--  * NAO ha soft delete (updated_at / removed_at) em conversations nem em
--    kb_chunks. Essas colunas nao existem em nenhuma migration ate a head.
--
-- Se a intencao for realmente mudar o schema (singular, enum, soft delete),
-- isso e uma NOVA migration + mudanca nos models do app, nao uma edicao manual
-- deste arquivo (editar aqui dessincronizaria o app da head carimbada).
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Extensoes
--   vector    -> tipo VECTOR e indice HNSW (RAG)
--   pgcrypto  -> gen_random_uuid() usado como default das PKs UUID
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------------------------------------------
-- kb_chunks: base de conhecimento do RAG (chunks + embedding 384d)
--   Sem dependencia de outras tabelas.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kb_chunks (
    id          UUID        NOT NULL DEFAULT gen_random_uuid(),
    source      VARCHAR(100) NOT NULL,
    content     TEXT        NOT NULL,
    embedding   VECTOR(384) NOT NULL,
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT kb_chunks_pkey PRIMARY KEY (id)
);

-- Indice vetorial HNSW com distancia de cosseno (NUNCA ivfflat: o ivfflat com
-- lists=100 sobre poucos vetores examinava 1 lista so e retornava quase nada,
-- foi a causa raiz do RAG quebrado). Parametros: m=16, ef_construction=64.
CREATE INDEX IF NOT EXISTS ix_kb_chunks_embedding
    ON kb_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ----------------------------------------------------------------------------
-- conversations: conversas da nutriz logada
--   FK fisica user_id -> "user"(id_user) [tabela do backend Go].
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id               UUID        NOT NULL DEFAULT gen_random_uuid(),
    user_id          VARCHAR(36) NOT NULL,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_message_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary          TEXT,
    CONSTRAINT conversations_pkey PRIMARY KEY (id),
    CONSTRAINT conversations_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES "user" (id_user)
);

CREATE INDEX IF NOT EXISTS ix_conversations_user_id
    ON conversations (user_id);
CREATE INDEX IF NOT EXISTS ix_conversations_last_message_at
    ON conversations (last_message_at);

-- ----------------------------------------------------------------------------
-- messages: mensagens de cada conversa (memoria curta)
--   role e VARCHAR(20) (user | assistant | system) — nao ha enum.
--   FK conversation_id -> conversations(id) ON DELETE CASCADE.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id               UUID        NOT NULL DEFAULT gen_random_uuid(),
    conversation_id  UUID        NOT NULL,
    role             VARCHAR(20) NOT NULL,
    content          TEXT        NOT NULL,
    tokens_used      INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT messages_pkey PRIMARY KEY (id),
    CONSTRAINT messages_conversation_id_fkey
        FOREIGN KEY (conversation_id) REFERENCES conversations (id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_messages_conversation_id
    ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS ix_messages_created_at
    ON messages (created_at);

-- ----------------------------------------------------------------------------
-- llm_audit: trilha LGPD append-only de TODA chamada a LLM.
--   SEM FK fisica de proposito: as referencias (user_id / conversation_id /
--   message_id) sao logicas, para a auditoria sobreviver a exclusao de dados
--   da nutriz (direito ao esquecimento). Todas nullable: registros anonimos
--   (modo publico) nao tem user_id/conversation_id/message_id.
--   prompt_full e JSONB. Rastreabilidade anonima por session_id + ip_hash.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_audit (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    user_id         VARCHAR(36),
    conversation_id UUID,
    message_id      UUID,
    prompt_full     JSONB       NOT NULL,
    chunks_used     JSONB,
    llm_provider    VARCHAR(30) NOT NULL,
    llm_model       VARCHAR(50) NOT NULL,
    tokens_input    INTEGER,
    tokens_output   INTEGER,
    latency_ms      INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_anonymous    BOOLEAN     NOT NULL DEFAULT false,
    session_id      VARCHAR(36),
    ip_hash         VARCHAR(64),
    action_emitted  VARCHAR(30),
    CONSTRAINT llm_audit_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_llm_audit_session_id
    ON llm_audit (session_id);

-- ----------------------------------------------------------------------------
-- alembic_version: carimba a head para o servico NAO rodar as migrations de
-- novo. OBRIGATORIO. Sem isto, na subida o servico tentaria criar tudo outra
-- vez e falharia (tabelas ja existem).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Insere a head somente se a tabela estiver vazia (idempotente).
INSERT INTO alembic_version (version_num)
    SELECT 'd4e91a7c22b0'
    WHERE NOT EXISTS (SELECT 1 FROM alembic_version);

COMMIT;
