from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    POSTGRES_USER: str = "neo"
    POSTGRES_PASSWORD: str = "neo_dev_password"
    POSTGRES_DB: str = "neodb"
    DATABASE_ASYNC_URL: str = "postgresql+asyncpg://neo:neo_dev_password@postgres:5432/neodb"
    DATABASE_SYNC_URL: str = "postgresql+psycopg://neo:neo_dev_password@postgres:5432/neodb"

    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"

    JWT_SECRET_KEY: str = "dev_only_secret_key_change_in_production_32chars_min"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    UPLOAD_DIR: str = "/app/data/uploads"
    MAX_IMAGE_BYTES: int = 10485760
    MAX_PDF_BYTES: int = 20971520
    MAX_PDF_PAGES: int = 30

    PRIMARY_LLM_MODEL: str = "gpt-4o-mini"
    FALLBACK_LLM_MODEL: str = "gemini-2.5-flash"
    VISION_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536
    OPENAI_API_KEY: str = "sk-placeholder"
    GEMINI_API_KEY: str = "placeholder"
    TAVILY_API_KEY: str = "tvly-placeholder"
    DEDUP_SIMILARITY_THRESHOLD: float = 0.92
    CONFLICT_SIMILARITY_THRESHOLD: float = 0.78


@lru_cache
def get_settings() -> Settings:
    return Settings()
