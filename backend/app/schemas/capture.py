import uuid
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class SourceTypeEnum(str, Enum):
    TEXT = "text"
    URL = "url"
    PDF = "pdf"
    IMAGE = "image"
    YOUTUBE = "youtube"


class ExtractionStatusEnum(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    FAILED = "failed"


# ---- Request bodies ----

class CaptureTextRequest(BaseModel):
    text: str = Field(min_length=3, max_length=50_000, description="Raw text to capture.")
    title: str | None = Field(default=None, max_length=500)


class CaptureUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    title: str | None = Field(default=None, max_length=500)

    @field_validator("url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        from urllib.parse import urlparse
        scheme = urlparse(v).scheme
        if scheme not in ("http", "https"):
            raise ValueError("Only http:// and https:// URLs are accepted.")
        return v


# ---- Response bodies ----

class CapturedItemResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    source_type: SourceTypeEnum
    title: str | None
    content_hash: str
    extraction_status: ExtractionStatusEnum
    celery_task_id: str | None = None


# ---- SSE event schemas ----

class SSEEventType(str, Enum):
    CAPTURE_QUEUED = "capture.queued"
    CAPTURE_STARTED = "capture.started"
    CAPTURE_DONE = "capture.done"
    CAPTURE_FAILED = "capture.failed"
    HEARTBEAT = "heartbeat"


class SSEEvent(BaseModel):
    event: SSEEventType
    item_id: str | None = None
    task_id: str | None = None
    message: str | None = None
