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


settings = Settings()
