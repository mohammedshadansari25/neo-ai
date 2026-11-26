from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# FastAPI async engine (asyncpg)
async_engine = create_async_engine(
    settings.DATABASE_ASYNC_URL,
    pool_size=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Celery isolated sync engine (psycopg + NullPool)
sync_engine = create_engine(
    settings.DATABASE_SYNC_URL,
    poolclass=NullPool,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
