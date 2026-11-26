import json
import uuid

import httpx
import pytest
from redis.asyncio import Redis

from app.config import get_settings
from app.main import app


def _parse_sse_events(raw_text: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for block in raw_text.strip().split("\n\n"):
        if not block or block.startswith(":"):
            continue
        event_id = ""
        data_line = ""
        for line in block.splitlines():
            if line.startswith("id: "):
                event_id = line[4:].strip()
            elif line.startswith("data: "):
                data_line = line[6:].strip()
        if event_id and data_line:
            events.append((event_id, json.loads(data_line)))
    return events


@pytest.mark.asyncio
async def test_spike_e_sse_bearer_auth_and_last_event_id_replay():
    """
    Spike E: Prove Bearer-authenticated SSE streaming over Redis Streams
    supports heartbeat pings and Last-Event-ID replay with 0 duplicates.
    """
    settings = get_settings()
    stream_key = f"spike:sse:{uuid.uuid4()}"
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)

    try:
        for seq in range(1, 6):
            await redis_client.xadd(
                stream_key,
                {"seq": str(seq), "data": f"event-{seq}"},
                maxlen=1000,
                approximate=True,
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Missing Bearer auth must return 401
            unauth = await client.get(f"/api/spikes/sse?stream_key={stream_key}")
            assert unauth.status_code == 401

            # 2. First connection receives events 1..3 + : ping heartbeat
            resp1 = await client.get(
                f"/api/spikes/sse?stream_key={stream_key}&max_events=3",
                headers={"Authorization": "Bearer spike-token"},
            )
            assert resp1.status_code == 200
            assert resp1.headers["cache-control"] == "no-cache"
            assert resp1.headers["x-accel-buffering"] == "no"
            assert ": ping" in resp1.text

            events1 = _parse_sse_events(resp1.text)
            assert [e[1]["seq"] for e in events1] == ["1", "2", "3"]
            last_id = events1[-1][0]

            # 3. Reconnect with Last-Event-ID receives events 4..5 with 0 duplicates
            resp2 = await client.get(
                f"/api/spikes/sse?stream_key={stream_key}&max_events=5",
                headers={
                    "Authorization": "Bearer spike-token",
                    "Last-Event-ID": last_id,
                },
            )
            assert resp2.status_code == 200
            events2 = _parse_sse_events(resp2.text)
            assert [e[1]["seq"] for e in events2] == ["4", "5"]

            all_ids = [e[0] for e in events1] + [e[0] for e in events2]
            assert len(all_ids) == len(set(all_ids)) == 5
    finally:
        await redis_client.delete(stream_key)
        await redis_client.aclose()
