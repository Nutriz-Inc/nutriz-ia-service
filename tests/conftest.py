# Fixtures compartilhadas da suite de testes.
#
# Decisoes:
# - Banco de teste dedicado (nutriz_ia_test) criado/destruido por sessao,
#   na mesma imagem pgvector/pgvector:pg16 do compose.
# - LLM sempre mockado (FakeProvider): nenhum teste depende do Groq real.
# - Embeddings mockados com vetores deterministicos (bag-of-words + projecao
#   pseudo-aleatoria por palavra): textos que compartilham palavras geram
#   vetores proximos, o que permite testar o ranking do RAG offline.
# - Variaveis de ambiente definidas ANTES de importar app.* para que o
#   Settings aponte para o banco de teste e use segredos ficticios.

import os
import zlib
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

TEST_DB_NAME = "nutriz_ia_test"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    f"postgresql+asyncpg://postgres:postgres@localhost:5433/{TEST_DB_NAME}",
)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "segredo-de-teste"
os.environ["GROQ_API_KEY"] = "chave-fake-de-teste"
os.environ["LLM_PROVIDER"] = "groq"

import jwt as pyjwt
import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401 - registra todas as tabelas no Base.metadata
from app.config import settings
from app.database import Base, get_db
from app.llm.provider import LLMProvider, get_llm_provider
from app.services.embeddings import embeddings_service


SEED_USER_ID = "f058115f-51cb-4eb6-b7b9-7e2397299641"
SEED_USER_NAME = "Usuaria Teste"


# ---------------------------------------------------------------------------
# Embeddings deterministicos (sem modelo real)
# ---------------------------------------------------------------------------

_EMBEDDING_DIM = 384


def _word_vector(word: str) -> np.ndarray:
    # crc32 e estavel entre processos (hash() do python e salteado)
    seed = zlib.crc32(word.lower().encode("utf-8"))
    rng = np.random.RandomState(seed)
    return rng.randn(_EMBEDDING_DIM)


def fake_encode(text_input: str) -> list[float]:
    words = text_input.split()
    if not words:
        vec = np.zeros(_EMBEDDING_DIM)
        vec[0] = 1.0
    else:
        vec = np.sum([_word_vector(w) for w in words], axis=0)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


@pytest.fixture(autouse=True)
def mock_embeddings(monkeypatch: pytest.MonkeyPatch):
    async def fake_encode_async(text_input: str) -> list[float]:
        return fake_encode(text_input)

    def fake_encode_batch(texts: list[str], show_progress: bool = False) -> list[list[float]]:
        return [fake_encode(t) for t in texts]

    monkeypatch.setattr(embeddings_service, "encode", fake_encode)
    monkeypatch.setattr(embeddings_service, "encode_async", fake_encode_async)
    monkeypatch.setattr(embeddings_service, "encode_batch", fake_encode_batch)
    yield


# ---------------------------------------------------------------------------
# Provider LLM falso (Strategy Pattern)
# ---------------------------------------------------------------------------

class FakeProvider(LLMProvider):
    """Implementa a interface do Strategy Pattern sem rede."""

    def __init__(self, chunks: tuple[str, ...] = ("Ola, ", "sou a EVA ", "de teste.")) -> None:
        self.chunks = chunks
        self.calls: list[list[dict[str, str]]] = []

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        self.calls.append(messages)
        for chunk in self.chunks:
            yield chunk

    def get_provider_name(self) -> str:
        return "fake"

    def get_model_name(self) -> str:
        return "fake-model"


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    provider = FakeProvider()
    # chat_ws resolve o provider pelo nome importado no modulo do router
    import app.routers.chat_ws as chat_ws_module

    monkeypatch.setattr(chat_ws_module, "get_llm_provider", lambda: provider)
    get_llm_provider.cache_clear()
    return provider


# ---------------------------------------------------------------------------
# Banco de teste (pgvector) criado por sessao
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def test_engine():
    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin_engine.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
        await conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    await admin_engine.dispose()

    # NullPool: conexoes novas por uso, evitando conflito entre o event loop
    # dos testes e o event loop interno do TestClient (WebSocket)
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    # Isolamento entre testes: trunca tudo apos cada teste que usou o banco.
    # Antes, derruba conexoes orfas (sessao do WS cancelada pelo TestClient
    # pode ficar "idle in transaction" e bloquear o TRUNCATE para sempre).
    async with test_engine.connect() as conn:
        await conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{TEST_DB_NAME}' AND pid <> pg_backend_pid()"
            )
        )
        await conn.execute(
            text(
                'TRUNCATE TABLE llm_audit, messages, conversations, kb_chunks, '
                'consent_log, user_baby, address, "user" CASCADE'
            )
        )
        await conn.commit()


# ---------------------------------------------------------------------------
# Seeds (user + consent + bebe + endereco)
# ---------------------------------------------------------------------------

def _naive_now() -> datetime:
    # Tabelas espelhadas do Go usam TIMESTAMP sem timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest_asyncio.fixture(loop_scope="session")
async def seed_user(db_session: AsyncSession) -> str:
    now = _naive_now()
    await db_session.execute(
        text(
            'INSERT INTO "user" (id_user, type, name, cpf, birth_date, phone_number, '
            "email, password, created_at, created_by) VALUES "
            "(:id, 'common', :name, '12345678901', :birth, '11999990000', "
            "'teste@nutriz.com', 'hash', :now, :id)"
        ),
        {"id": SEED_USER_ID, "name": SEED_USER_NAME, "birth": now - timedelta(days=365 * 30), "now": now},
    )
    await db_session.commit()
    return SEED_USER_ID


@pytest_asyncio.fixture(loop_scope="session")
async def seed_consent(db_session: AsyncSession, seed_user: str) -> str:
    await db_session.execute(
        text(
            "INSERT INTO consent_log (id_consent_log, id_user, terms_version, "
            "accepted_at, ip_address, user_agent) VALUES "
            "('11111111-1111-1111-1111-111111111111', :id, 'v1.0', :now, '127.0.0.1', 'pytest')"
        ),
        {"id": seed_user, "now": _naive_now()},
    )
    await db_session.commit()
    return seed_user


@pytest_asyncio.fixture(loop_scope="session")
async def seed_baby_and_address(db_session: AsyncSession, seed_user: str) -> str:
    now = _naive_now()
    await db_session.execute(
        text(
            "INSERT INTO user_baby (id_user_baby, id_user, name, birth_date, created_at) "
            "VALUES ('22222222-2222-2222-2222-222222222222', :id, 'Joao', :birth, :now)"
        ),
        {"id": seed_user, "birth": now - timedelta(days=120), "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO address (id_address, id_user, zipcode, street, number, "
            "neighborhood, city, state, created_at) VALUES "
            "('33333333-3333-3333-3333-333333333333', :id, '04101000', 'Rua Teste', '10', "
            "'Vila Mariana', 'Sao Paulo', 'SP', :now)"
        ),
        {"id": seed_user, "now": now},
    )
    await db_session.commit()
    return seed_user


# ---------------------------------------------------------------------------
# JWT de teste
# ---------------------------------------------------------------------------

def make_token(
    user_id: str = SEED_USER_ID,
    expires_in: timedelta = timedelta(hours=1),
    secret: str | None = None,
) -> str:
    exp = int((datetime.now(timezone.utc) + expires_in).timestamp())
    return pyjwt.encode(
        {"id_user": user_id, "exp": exp},
        secret or settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


@pytest.fixture
def valid_token() -> str:
    return make_token()


# ---------------------------------------------------------------------------
# App com dependencias sobrescritas
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="session")
async def app_with_overrides(test_engine, fake_provider: FakeProvider):
    from app.main import app

    maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()
