import uuid

import httpx
import pytest
from sqlalchemy import text

from app.db.session import async_engine
from app.main import app


@pytest.mark.asyncio
async def test_auth_lifecycle_and_health():
    email = f"neo-{uuid.uuid4().hex[:10]}@example.com"
    password = "StrongPassword123!"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health endpoints
        live = await client.get("/health/live")
        assert live.status_code == 200
        assert live.json() == {"status": "ok"}

        ready = await client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {"postgres": "ok", "redis": "ok"}

        # 2. Register
        reg = await client.post("/api/auth/register", json={"email": email, "password": password})
        assert reg.status_code == 201
        reg_body = reg.json()
        assert reg_body["token_type"] == "bearer"
        assert reg_body["user"]["email"] == email
        access_token = reg_body["access_token"]
        assert "neo_refresh" in client.cookies

        # Duplicate register -> 409
        dup = await client.post("/api/auth/register", json={"email": email, "password": password})
        assert dup.status_code == 409

        # 3. /api/me protected
        me_unauth = await client.get("/api/me")
        assert me_unauth.status_code == 401

        me_ok = await client.get("/api/me", headers={"Authorization": f"Bearer {access_token}"})
        assert me_ok.status_code == 200
        assert me_ok.json()["email"] == email

        # 4. Login (wrong password -> 401, right password -> 200)
        bad_login = await client.post("/api/auth/login", json={"email": email, "password": "wrongpass"})
        assert bad_login.status_code == 401

        good_login = await client.post("/api/auth/login", json={"email": email, "password": password})
        assert good_login.status_code == 200
        old_refresh = client.cookies.get("neo_refresh")
        assert old_refresh is not None

        # 5. Refresh rotation
        refreshed = await client.post("/api/auth/refresh")
        assert refreshed.status_code == 200
        new_refresh = client.cookies.get("neo_refresh")
        assert new_refresh is not None and new_refresh != old_refresh

        # Replaying old revoked refresh token -> 401
        client.cookies.set("neo_refresh", old_refresh)
        replay = await client.post("/api/auth/refresh")
        assert replay.status_code == 401

        # 6. Logout revokes active refresh token
        client.cookies.set("neo_refresh", new_refresh)
        logged_out = await client.post("/api/auth/logout")
        assert logged_out.status_code == 200
        assert logged_out.json() == {"ok": True}

    # Cleanup test user
    async with async_engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
