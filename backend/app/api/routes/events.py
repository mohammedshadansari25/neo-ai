import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.config import get_settings
from app.core.security import get_current_user
from app.db.models import User

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/stream")
async def events_stream(
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Authenticated SSE stream scoped strictly to `current_user.id`.
    Supports Last-Event-ID replay via Redis Streams XRANGE.
    Frontend MUST connect using fetch() + ReadableStream, NOT native EventSource.
    """
    settings = get_settings()
    user_id = str(current_user.id)
    stream_key = f"neo:events:{user_id}"

    async def event_generator():
        redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            yield ": ping\n\n"
            last_id = "$"

            while True:
                raw = await redis_client.xread({stream_key: last_id}, count=50, block=5000)
                if not raw:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(0)
                    continue

                for _key, messages in raw:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        payload_str = fields.get("payload", "{}")
                        try:
                            payload = json.loads(payload_str)
                        except json.JSONDecodeError:
                            payload = {"raw": payload_str}

                        event_type = payload.get("event", "message")
                        data = json.dumps(payload)
                        yield f"id: {msg_id}\nevent: {event_type}\ndata: {data}\n\n"
        except asyncio.CancelledError:
            pass
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
