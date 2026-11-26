import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.guards import (
    MagicByteError,
    SSRFBlockedError,
    sha256_hex,
    sha256_text,
    validate_file_magic,
    validate_ssrf,
)
from app.core.security import get_current_user
from app.db.models import CapturedItem, User
from app.db.session import get_db
from app.schemas.capture import (
    CapturedItemResponse,
    CaptureTextRequest,
    CaptureUrlRequest,
    ExtractionStatusEnum,
    SourceTypeEnum,
)
from app.worker.extraction import extract_item_task

router = APIRouter(prefix="/api/capture", tags=["capture"])


async def _get_or_create_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_type: SourceTypeEnum,
    content_hash: str,
    title: str | None,
    raw_text: str | None = None,
    raw_uri: str | None = None,
    storage_path: str | None = None,
) -> tuple[CapturedItem, bool]:
    """
    Idempotent upsert: returns (item, created).
    If a non-failed row with the same (user_id, content_hash) exists, return it.
    """
    existing = (
        await db.execute(
            select(CapturedItem).where(
                CapturedItem.user_id == user_id,
                CapturedItem.content_hash == content_hash,
                CapturedItem.extraction_status != ExtractionStatusEnum.FAILED,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing, False

    item = CapturedItem(
        user_id=user_id,
        source_type=source_type,
        title=title,
        content_hash=content_hash,
        raw_text=raw_text,
        raw_uri=raw_uri,
        storage_path=storage_path,
        extraction_status=ExtractionStatusEnum.QUEUED,
    )
    db.add(item)
    await db.flush()
    return item, True


@router.post("/text", response_model=CapturedItemResponse, status_code=202)
async def capture_text(
    body: CaptureTextRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CapturedItemResponse:
    content_hash = sha256_text(body.text)
    item, created = await _get_or_create_item(
        db,
        user_id=current_user.id,
        source_type=SourceTypeEnum.TEXT,
        content_hash=content_hash,
        title=body.title,
        raw_text=body.text,
    )
    await db.commit()

    task_id: str | None = None
    if created:
        result = extract_item_task.delay(str(item.id), str(current_user.id))
        task_id = result.id

    return CapturedItemResponse(
        id=item.id,
        user_id=item.user_id,
        source_type=SourceTypeEnum(item.source_type),
        title=item.title,
        content_hash=item.content_hash,
        extraction_status=ExtractionStatusEnum(item.extraction_status),
        celery_task_id=task_id,
    )


@router.post("/url", response_model=CapturedItemResponse, status_code=202)
async def capture_url(
    body: CaptureUrlRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CapturedItemResponse:
    try:
        validated_url = validate_ssrf(body.url)
    except SSRFBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    content_hash = sha256_text(validated_url)
    item, created = await _get_or_create_item(
        db,
        user_id=current_user.id,
        source_type=SourceTypeEnum.URL,
        content_hash=content_hash,
        title=body.title or validated_url[:200],
        raw_uri=validated_url,
    )
    await db.commit()

    task_id: str | None = None
    if created:
        result = extract_item_task.delay(str(item.id), str(current_user.id))
        task_id = result.id

    return CapturedItemResponse(
        id=item.id,
        user_id=item.user_id,
        source_type=SourceTypeEnum(item.source_type),
        title=item.title,
        content_hash=item.content_hash,
        extraction_status=ExtractionStatusEnum(item.extraction_status),
        celery_task_id=task_id,
    )


@router.post("/file", response_model=CapturedItemResponse, status_code=202)
async def capture_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CapturedItemResponse:
    settings = get_settings()

    # Size guard before reading fully
    max_bytes = max(settings.MAX_PDF_BYTES, settings.MAX_IMAGE_BYTES)
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size ({max_bytes // 1_048_576} MB).",
        )

    # Magic-byte validation
    try:
        detected = validate_file_magic(data)
    except MagicByteError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    # Per-type size limits
    if detected == "pdf" and len(data) > settings.MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds 20 MB limit.")
    if detected in ("png", "jpeg", "webp") and len(data) > settings.MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit.")

    import os

    source_type = SourceTypeEnum.PDF if detected == "pdf" else SourceTypeEnum.IMAGE
    content_hash = sha256_hex(data)

    # Persist raw bytes to upload dir scoped by user_id
    upload_root = settings.UPLOAD_DIR
    user_dir = f"{upload_root}/{current_user.id}"
    filename = file.filename or f"{content_hash}.{detected}"
    storage_path = f"{user_dir}/{content_hash}_{filename}"

    os.makedirs(user_dir, exist_ok=True)
    if not os.path.exists(storage_path):
        with open(storage_path, "wb") as fh:  # noqa: ASYNC230
            fh.write(data)

    item, created = await _get_or_create_item(
        db,
        user_id=current_user.id,
        source_type=source_type,
        content_hash=content_hash,
        title=filename[:500],
        storage_path=storage_path,
    )
    await db.commit()

    task_id: str | None = None
    if created:
        result = extract_item_task.delay(str(item.id), str(current_user.id))
        task_id = result.id

    return CapturedItemResponse(
        id=item.id,
        user_id=item.user_id,
        source_type=SourceTypeEnum(item.source_type),
        title=item.title,
        content_hash=item.content_hash,
        extraction_status=ExtractionStatusEnum(item.extraction_status),
        celery_task_id=task_id,
    )
