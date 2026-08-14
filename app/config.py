import ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

# Parametros so do libpq/psycopg (a string do Neon vem com ?sslmode=require) que
# o driver asyncpg nao aceita como kwargs de connect(). O SSL vai por connect_args.
_LIBPQ_ONLY_PARAMS = {
    "sslmode",
    "channel_binding",
    "sslrootcert",
    "sslcert",
    "sslkey",
    "gssencmode",
}
_SSL_MODES_REQUIRING_SSL = {"require", "verify-ca", "verify-full", "prefer", "allow"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    LLM_PROVIDER: str = "groq"
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    OLLAMA_MODEL: str = "llama3.2:3b"
    # Diretorio com o artefato ONNX de embeddings (model.onnx + tokenizer.json)
    # de vocabulario podado (250k->50k tokens). Ver docs/otimizacao-memoria.md.
    EMBEDDINGS_MODEL_DIR: str = "/models"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Modo publico (chat anonimo sem login)
    ANON_SESSION_TTL_MINUTES: int = 30
    ANON_RATE_LIMIT_PER_IP_HOUR: int = 30
    ANON_RATE_LIMIT_PER_SESSION: int = 10
    ANON_MAX_JAILBREAK_STRIKES: int = 3
    # Origens permitidas no CORS (front Vite roda em 5173). Lista separada por virgula.
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        # Provedores gerenciados (ex.: Render/Neon) entregam a URL como
        # postgres:// ou postgresql:// e com parametros do libpq (ex.:
        # ?sslmode=require). Normaliza o esquema para o driver assincrono
        # asyncpg e remove os parametros que ele nao aceita (o SSL vai por
        # db_connect_args), sem exigir que quem cola a URL saiba desse detalhe.
        url = self.DATABASE_URL
        for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                url = "postgresql+asyncpg://" + url[len(prefix) :]
                break
        parts = urlsplit(url)
        params = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k not in _LIBPQ_ONLY_PARAMS
        ]
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment)
        )

    @property
    def db_connect_args(self) -> dict:
        # asyncpg espera o SSL via contexto (nao via ?sslmode). Neon exige SSL;
        # detecta pelo sslmode da URL original e entrega um contexto padrao
        # (verifica o certificado - o Neon tem cert valido). Local sem sslmode
        # segue sem SSL.
        params = dict(parse_qsl(urlsplit(self.DATABASE_URL).query))
        if params.get("sslmode", "").lower() in _SSL_MODES_REQUIRING_SSL:
            return {"ssl": ssl.create_default_context()}
        return {}


settings = Settings()
