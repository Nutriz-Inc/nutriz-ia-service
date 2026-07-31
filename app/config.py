from pydantic_settings import BaseSettings, SettingsConfigDict


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
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
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
        # Provedores gerenciados (ex.: Render) entregam a URL como
        # postgres:// ou postgresql://, mas o app usa o driver assincrono
        # asyncpg. Normaliza o esquema para postgresql+asyncpg:// sem exigir
        # que quem configura o ambiente saiba desse detalhe.
        url = self.DATABASE_URL
        for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url[len(prefix) :]
        return url


settings = Settings()
