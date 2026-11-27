from functools import lru_cache
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_celery_broker_url(redis_url: str) -> str:
    parsed = urlparse(redis_url)
    if parsed.path in ("", "/", "/0"):
        return urlunparse(parsed._replace(path="/1"))
    return redis_url


def _default_upload_dir() -> str:
    app_uploads = Path("/app/data/uploads")
    try:
        app_uploads.mkdir(parents=True, exist_ok=True)
        if os.access(app_uploads, os.W_OK):
            return str(app_uploads)
    except OSError:
        pass
    fallback = Path("data/uploads").resolve()
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    POSTGRES_USER: str = "neo"
    POSTGRES_PASSWORD: str = "neo_dev_password"
    POSTGRES_DB: str = "neodb"
    DATABASE_ASYNC_URL: str = "postgresql+asyncpg://neo:neo_dev_password@postgres:5432/neodb"
    DATABASE_SYNC_URL: str = "postgresql+psycopg://neo:neo_dev_password@postgres:5432/neodb"

    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = ""

    JWT_SECRET_KEY: str = "dev_only_secret_key_change_in_production_32chars_min"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    UPLOAD_DIR: str = ""
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

    @model_validator(mode="after")
    def _populate_derived_defaults(self) -> "Settings":
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = _default_celery_broker_url(self.REDIS_URL)
        if not self.UPLOAD_DIR:
            self.UPLOAD_DIR = _default_upload_dir()
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
