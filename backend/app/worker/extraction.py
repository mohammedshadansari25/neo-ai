import json
from typing import Any

import pymupdf
import trafilatura
from celery import Task
from PIL import Image
from sqlalchemy import text

from app.config import get_settings
from app.worker.celery_app import celery_app, sync_engine


def _publish_sse_event(redis_url: str, user_id: str, event: dict[str, Any]) -> None:
    """Push a JSON event to the user-scoped Redis Stream for SSE replay."""
    import redis as redis_sync  # sync redis for Celery workers

    r = redis_sync.from_url(redis_url, decode_responses=True)
    stream_key = f"neo:events:{user_id}"
    r.xadd(stream_key, {"payload": json.dumps(event)}, maxlen=1000, approximate=True)
    r.close()


def _extract_text_content(raw_text: str | None) -> str:
    return (raw_text or "").strip()


def _extract_url_content(raw_uri: str | None) -> str:
    if not raw_uri:
        return ""
    try:
        downloaded = trafilatura.fetch_url(raw_uri)
        if downloaded:
            extracted = trafilatura.extract(downloaded, include_comments=False)
            return (extracted or "").strip()
    except Exception as exc:  # noqa: BLE001
        # URL fetch/parse failure is non-fatal; return empty string for downstream LLM enrichment
        return f"[fetch_error: {exc!s:.200}]"
    return ""


def _extract_pdf_content(storage_path: str, max_pages: int) -> str:
    doc = pymupdf.open(storage_path)
    pages = []
    for idx in range(min(doc.page_count, max_pages)):
        page = doc.load_page(idx)
        page_text = page.get_text("text").strip()
        if len(page_text) >= 50:
            pages.append(page_text)
        else:
            # Scanned page: render at 150 DPI and encode dimensions as placeholder
            pix = page.get_pixmap(dpi=150)
            pages.append(f"[scanned_page:{idx+1}:{pix.width}x{pix.height}]")
    return "\n\n".join(pages)


def _extract_image_content(storage_path: str) -> str:
    with Image.open(storage_path) as img:
        w, h = img.size
    return f"[image:{w}x{h}]"


@celery_app.task(
    bind=True,
    name="extract_item",
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
    reject_on_worker_lost=True,
)
def extract_item_task(self: Task, item_id: str, user_id: str) -> dict[str, str]:
    settings = get_settings()
    redis_url = settings.REDIS_URL

    def _publish(event_type: str, **extra: Any) -> None:
        _publish_sse_event(
            redis_url,
            user_id,
            {"event": event_type, "item_id": item_id, "task_id": self.request.id, **extra},
        )

    _publish("capture.started")

    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT source_type, raw_text, raw_uri, storage_path, extraction_status "
                "FROM captured_items WHERE id = :id AND user_id = :uid"
            ),
            {"id": item_id, "uid": user_id},
        ).fetchone()

    if row is None:
        return {"status": "not_found", "item_id": item_id}

    source_type = row.source_type
    try:
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE captured_items SET extraction_status = 'processing', updated_at = now() "
                    "WHERE id = :id AND user_id = :uid"
                ),
                {"id": item_id, "uid": user_id},
            )

        extracted_text: str = ""
        if source_type == "text":
            extracted_text = _extract_text_content(row.raw_text)
        elif source_type == "url":
            extracted_text = _extract_url_content(row.raw_uri)
        elif source_type == "pdf":
            extracted_text = _extract_pdf_content(row.storage_path, settings.MAX_PDF_PAGES)
        elif source_type == "image":
            extracted_text = _extract_image_content(row.storage_path)

        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE captured_items "
                    "SET extraction_status = 'completed', raw_text = :txt, updated_at = now() "
                    "WHERE id = :id AND user_id = :uid"
                ),
                {"id": item_id, "uid": user_id, "txt": extracted_text},
            )

        _publish("capture.done")
        return {"status": "completed", "item_id": item_id}

    except Exception as exc:  # noqa: BLE001
        # Record failure, publish SSE, then retry (Celery max_retries=3)
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE captured_items "
                    "SET extraction_status = 'failed', error_message = :err, updated_at = now() "
                    "WHERE id = :id AND user_id = :uid"
                ),
                {"id": item_id, "uid": user_id, "err": str(exc)[:1000]},
            )
        _publish("capture.failed", error=str(exc)[:200])
        raise self.retry(exc=exc)
