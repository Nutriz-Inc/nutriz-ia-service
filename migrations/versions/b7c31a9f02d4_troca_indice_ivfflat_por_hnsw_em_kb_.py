"""troca indice ivfflat por hnsw em kb_chunks

O indice ivfflat foi criado na migration inicial sobre a tabela vazia:
os centroides das listas ficam degenerados e, com o default
ivfflat.probes = 1, a busca examina 1 de 100 listas e retorna quase
nenhum vizinho real (recall ~0). O RAG entao recebia apenas chunks
irrelevantes, descartados pelo threshold de score, e a EVA respondia
sempre sem contexto documental.

HNSW constroi o grafo incrementalmente a cada insert, entao funciona
corretamente mesmo criado antes da ingestao — adequado tambem a bases
pequenas como a atual.

Revision ID: b7c31a9f02d4
Revises: 4590891f6a01
Create Date: 2026-07-03

"""
from alembic import op


revision = "b7c31a9f02d4"
down_revision = "4590891f6a01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_embedding")
    op.execute(
        "CREATE INDEX ix_kb_chunks_embedding "
        "ON kb_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_embedding")
    op.execute(
        "CREATE INDEX ix_kb_chunks_embedding "
        "ON kb_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
