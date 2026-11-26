import pytest_asyncio

from app.db.session import async_engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_async_engine():
    yield
    await async_engine.dispose()
