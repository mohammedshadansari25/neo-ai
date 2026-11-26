import asyncio
import json
import uuid
from enum import Enum
from typing import Any, cast

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.routes.auth import router as auth_router
from app.api.routes.capture import router as capture_router
from app.api.routes.events import router as events_router
from app.config import get_settings
from app.db.session import async_engine

settings = get_settings()

app = FastAPI(title="Neo AI V1", version="0.1.0")
app.include_router(auth_router)
app.include_router(capture_router)
app.include_router(events_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[dict[str, object]] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    payload = ErrorEnvelope(
        error=ErrorDetail(
            code="validation_error",
            message="Request validation failed",
            request_id=request_id,
            details=[{"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in errors],
        )
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    status_code = exc.status_code if isinstance(exc, HTTPException) else 500
    detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
    payload = ErrorEnvelope(
        error=ErrorDetail(
            code=f"http_{status_code}",
            message=str(detail),
            request_id=request_id,
            details=[],
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> dict[str, str]:
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"postgres_unavailable: {exc}") from exc

    redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    try:
        pong = await redis_client.ping()
        if not pong:
            raise HTTPException(status_code=503, detail="redis_ping_failed")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"redis_unavailable: {exc}") from exc
    finally:
        await redis_client.aclose()

    return {"postgres": "ok", "redis": "ok"}


# --- Spike E: Authenticated SSE with Redis Streams & Last-Event-ID replay ---
@app.get("/api/spikes/sse")
async def spike_sse_stream(
    stream_key: str = "spike:sse:default",
    max_events: int = 5,
    authorization: str | None = Header(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Bearer token")

    async def event_generator():
        redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        sent = 0
        try:
            yield ": ping\n\n"
            start_id = f"({last_event_id}" if last_event_id else "-"
            raw_entries = await redis_client.xrange(
                stream_key, min=start_id, max="+", count=max_events
            )
            entries = cast(list[tuple[str, dict[str, Any]]], raw_entries or [])
            for msg_id, fields in entries:
                payload = json.dumps({"seq": fields.get("seq"), "data": fields.get("data")})
                yield f"id: {msg_id}\nevent: spike.step\ndata: {payload}\n\n"
                sent += 1
                if sent >= max_events:
                    break
                await asyncio.sleep(0.01)
        finally:
            await redis_client.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# --- Spike F: Contract Generation with Pydantic v2 Enum + Union + 422 ---
class SpikeSourceType(str, Enum):
    TEXT = "text"
    URL = "url"
    PDF = "pdf"


class TextPayload(BaseModel):
    kind: SpikeSourceType = SpikeSourceType.TEXT
    text: str = Field(min_length=3, max_length=50000)


class UrlPayload(BaseModel):
    kind: SpikeSourceType = SpikeSourceType.URL
    url: str = Field(min_length=8)


class SpikeContractRequest(BaseModel):
    payload: TextPayload | UrlPayload


class SpikeContractResponse(BaseModel):
    accepted: bool
    kind: SpikeSourceType


@app.post(
    "/api/spikes/contract-check",
    response_model=SpikeContractResponse,
    responses={422: {"model": ErrorEnvelope}},
)
async def spike_contract_check(body: SpikeContractRequest) -> SpikeContractResponse:
    return SpikeContractResponse(accepted=True, kind=body.payload.kind)
