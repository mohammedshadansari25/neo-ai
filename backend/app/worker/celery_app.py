import time

from celery import Celery
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# Isolated Sync SQLAlchemy engine for Celery (never share asyncpg engine across fork)
sync_engine = create_engine(
    settings.DATABASE_SYNC_URL,
    poolclass=NullPool,
)

celery_app = Celery(
    "neo_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(bind=True, name="spike_c_insert_row", max_retries=3)
def spike_c_insert_row(self, idempotency_key: str, delay_seconds: float = 0.0) -> dict[str, str]:
    """Spike C task: simulates slow work and performs an idempotent sync Postgres upsert."""
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    with sync_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO spike_c_jobs (idempotency_key, status)
                VALUES (:key, 'completed')
                ON CONFLICT (idempotency_key) DO NOTHING
                """
            ),
            {"key": idempotency_key},
        )
    return {"idempotency_key": idempotency_key, "status": "completed"}
