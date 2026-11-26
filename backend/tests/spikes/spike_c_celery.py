import uuid

from sqlalchemy import text

from app.worker.celery_app import spike_c_insert_row, sync_engine


def test_spike_c_celery_sync_idempotent_execution():
    """
    Spike C: Prove Celery + Redis + Sync Postgres (psycopg + NullPool)
    executes cleanly and preserves idempotency on duplicate delivery.
    (Mid-run SIGKILL recovery is additionally verified via docker compose kill -s SIGKILL worker.)
    """
    key = f"spike-c-{uuid.uuid4()}"

    with sync_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS spike_c_jobs (
                    idempotency_key TEXT PRIMARY KEY,
                    status TEXT NOT NULL
                )
                """
            )
        )

    try:
        async_result_1 = spike_c_insert_row.delay(idempotency_key=key, delay_seconds=0.1)
        res1 = async_result_1.get(timeout=15)
        assert res1["status"] == "completed"

        # Duplicate delivery with same idempotency_key must not fail or duplicate rows
        async_result_2 = spike_c_insert_row.delay(idempotency_key=key, delay_seconds=0.0)
        res2 = async_result_2.get(timeout=15)
        assert res2["status"] == "completed"

        with sync_engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM spike_c_jobs WHERE idempotency_key = :k"),
                {"k": key},
            ).scalar_one()
        assert count == 1, f"Expected 1 row, found {count}"
    finally:
        with sync_engine.begin() as conn:
            conn.execute(text("DELETE FROM spike_c_jobs WHERE idempotency_key = :k"), {"k": key})
