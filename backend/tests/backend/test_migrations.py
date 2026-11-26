import pytest
from sqlalchemy import text

from app.db.session import async_engine

EXPECTED_TABLES = {
    "users",
    "refresh_tokens",
    "captured_items",
    "memories",
    "memory_sources",
    "memory_links",
    "goals",
    "open_loops",
    "agent_runs",
    "agent_traces",
}


@pytest.mark.asyncio
async def test_migration_0001_tables_and_indexes_exist():
    async with async_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public'"
                )
            )
        ).fetchall()
        tables = {r[0] for r in rows}
        missing = EXPECTED_TABLES - tables
        assert not missing, f"Missing tables after migration: {missing}"

        indexes = (
            await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'memories'"
                )
            )
        ).fetchall()
        index_names = {r[0] for r in indexes}
        assert "idx_memories_emb" in index_names
        assert "idx_memories_tsv" in index_names
        assert "idx_memories_user_active" in index_names
