import io
import uuid

import httpx
import pymupdf
import pytest
from PIL import Image
from sqlalchemy import text

from app.core.guards import (
    MagicByteError,
    SSRFBlockedError,
    sha256_text,
    validate_file_magic,
    validate_ssrf,
)
from app.db.session import async_engine
from app.main import app

# --- SSRF Guard Unit Tests ---

def test_ssrf_blocks_loopback():
    with pytest.raises(SSRFBlockedError):
        validate_ssrf("http://127.0.0.1/secret")


def test_ssrf_blocks_private_ip():
    with pytest.raises(SSRFBlockedError):
        validate_ssrf("http://192.168.1.1/admin")


def test_ssrf_blocks_non_http_scheme():
    with pytest.raises(SSRFBlockedError):
        validate_ssrf("file:///etc/passwd")


def test_ssrf_allows_public_url():
    # Does not raise — just validates scheme/IP; no live DNS in CI
    result = validate_ssrf("https://example.com/page")
    assert result == "https://example.com/page"


# --- Magic-Byte Validation Unit Tests ---

def _make_png() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), "white")
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Neo AI V1 Spike B PDF test.")
    return doc.tobytes()


def test_magic_pdf():
    assert validate_file_magic(_make_pdf()) == "pdf"


def test_magic_png():
    assert validate_file_magic(_make_png()) == "png"


def test_magic_jpeg():
    jpeg_magic = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    assert validate_file_magic(jpeg_magic) == "jpeg"


def test_magic_invalid():
    with pytest.raises(MagicByteError):
        validate_file_magic(b"INVALIDHEADER12345")


# --- Capture API Integration Tests ---

@pytest.mark.asyncio
async def test_capture_text_dedup_and_lifecycle():
    email = f"cap-{uuid.uuid4().hex[:8]}@example.com"
    password = "CapturePass1!"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/auth/register", json={"email": email, "password": password})
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        # First capture
        r1 = await client.post(
            "/api/capture/text",
            json={"text": "Neo AI V1 Day 2 test capture content", "title": "Test Note"},
            headers=auth,
        )
        assert r1.status_code == 202
        body1 = r1.json()
        assert body1["extraction_status"] == "queued"
        assert body1["content_hash"] == sha256_text("Neo AI V1 Day 2 test capture content")
        item_id = body1["id"]

        # Duplicate capture -> same item, no new Celery task
        r2 = await client.post(
            "/api/capture/text",
            json={"text": "Neo AI V1 Day 2 test capture content"},
            headers=auth,
        )
        assert r2.status_code == 202
        assert r2.json()["id"] == item_id
        assert r2.json()["celery_task_id"] is None

        # Cross-user isolation: other user cannot see item via different JWT
        email2 = f"other-{uuid.uuid4().hex[:8]}@example.com"
        reg2 = await client.post("/api/auth/register", json={"email": email2, "password": password})
        token2 = reg2.json()["access_token"]
        r3 = await client.post(
            "/api/capture/text",
            json={"text": "Neo AI V1 Day 2 test capture content"},
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert r3.status_code == 202
        # Different user gets a new item (tenant isolation)
        assert r3.json()["id"] != item_id

    # Cleanup
    async with async_engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email IN (:e1, :e2)"), {"e1": email, "e2": email2})


@pytest.mark.asyncio
async def test_capture_url_ssrf_blocked():
    email = f"ssrf-{uuid.uuid4().hex[:8]}@example.com"
    password = "SSRFtest1!"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/auth/register", json={"email": email, "password": password})
        token = reg.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        r = await client.post(
            "/api/capture/url",
            json={"url": "http://127.0.0.1/admin"},
            headers=auth,
        )
        assert r.status_code == 422

        r2 = await client.post(
            "/api/capture/url",
            json={"url": "file:///etc/passwd"},
            headers=auth,
        )
        assert r2.status_code == 422

    async with async_engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


@pytest.mark.asyncio
async def test_capture_file_magic_rejection():
    email = f"file-{uuid.uuid4().hex[:8]}@example.com"
    password = "FileTest1!"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/auth/register", json={"email": email, "password": password})
        token = reg.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        # Random bytes -> rejected
        r = await client.post(
            "/api/capture/file",
            files={"file": ("evil.bin", b"RANDOMGARBAGE123", "application/octet-stream")},
            headers=auth,
        )
        assert r.status_code == 415

        # Valid PNG -> accepted
        png_bytes = _make_png()
        r2 = await client.post(
            "/api/capture/file",
            files={"file": ("test.png", png_bytes, "image/png")},
            headers=auth,
        )
        assert r2.status_code == 202
        assert r2.json()["source_type"] == "image"

    async with async_engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
