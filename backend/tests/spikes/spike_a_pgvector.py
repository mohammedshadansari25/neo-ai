import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


@pytest.mark.asyncio
async def test_spike_a_pgvector_iterative_scan():
    """
    Spike A: Verify pgvector >= 0.8.0 hnsw.iterative_scan = 'strict_order'
    preserves 100% recall on sparse user_id subsets without post-filter starvation.
    """
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_ASYNC_URL)

    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    dim = settings.EMBEDDING_DIM

    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            ext_row = (
                await conn.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
            ).fetchone()
            assert ext_row is not None, "pgvector extension not installed"
            version_parts = tuple(int(p) for p in ext_row[0].split(".")[:2])
            assert version_parts >= (0, 8), f"Expected pgvector >= 0.8, got {ext_row[0]}"

            await conn.execute(text("DROP TABLE IF EXISTS spike_a_vectors"))
            await conn.execute(
                text(
                    f"""
                    CREATE TABLE spike_a_vectors (
                        id UUID PRIMARY KEY,
                        user_id UUID NOT NULL,
                        embedding VECTOR({dim}) NOT NULL
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE INDEX idx_spike_a_hnsw
                    ON spike_a_vectors USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64)
                    """
                )
            )

            # Seed 500 vectors for User A (close to [1, 0, 0, ...])
            vec_a = "[" + ",".join(["1.0"] + ["0.0"] * (dim - 1)) + "]"
            rows_a = [{"id": str(uuid.uuid4()), "uid": user_a, "emb": vec_a} for _ in range(500)]
            await conn.execute(
                text(
                    "INSERT INTO spike_a_vectors (id, user_id, embedding) "
                    "VALUES (:id, :uid, CAST(:emb AS vector))"
                ),
                rows_a,
            )

            # Seed 5 vectors for User B (orthogonal [0, 1, 0, ...])
            vec_b = "[" + ",".join(["0.0", "1.0"] + ["0.0"] * (dim - 2)) + "]"
            rows_b = [{"id": str(uuid.uuid4()), "uid": user_b, "emb": vec_b} for _ in range(5)]
            await conn.execute(
                text(
                    "INSERT INTO spike_a_vectors (id, user_id, embedding) "
                    "VALUES (:id, :uid, CAST(:emb AS vector))"
                ),
                rows_b,
            )

        # Query User B using strict_order iterative scan inside a transaction
        async with engine.begin() as conn:
            await conn.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
            t0 = time.perf_counter()
            result = await conn.execute(
                text(
                    """
                    SELECT id, user_id
                    FROM spike_a_vectors
                    WHERE user_id = :uid
                    ORDER BY embedding <=> CAST(:qvec AS vector)
                    LIMIT 5
                    """
                ),
                {"uid": user_b, "qvec": vec_a},
            )
            rows = result.fetchall()
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert len(rows) == 5, f"Expected 5 User B rows, got {len(rows)}"
        assert all(str(r.user_id) == user_b for r in rows)
        assert elapsed_ms < 50.0, f"Query took {elapsed_ms:.2f}ms (limit 50ms)"
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS spike_a_vectors"))
        await engine.dispose()
