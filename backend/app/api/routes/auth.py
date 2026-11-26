from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    get_current_user,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.models import RefreshToken, User
from app.db.session import get_db
from app.schemas.auth import (
    AuthRequest,
    LogoutResponse,
    TokenResponse,
    UserProfileResponse,
)

router = APIRouter(tags=["auth"])
REFRESH_COOKIE_NAME = "neo_refresh"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth",
    )


async def _issue_tokens(db: AsyncSession, response: Response, user: User) -> TokenResponse:
    settings = get_settings()
    raw_refresh, refresh_hash = generate_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=expires_at,
        )
    )
    await db.commit()

    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserProfileResponse(
            id=user.id,
            email=user.email,
            profile_summary=user.profile_summary,
        ),
    )


@router.post("/api/auth/register", response_model=TokenResponse, status_code=201)
async def register(
    body: AuthRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    existing = (
        await db.execute(select(User).where(func.lower(User.email) == body.email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        profile_summary={},
    )
    db.add(user)
    await db.flush()
    return await _issue_tokens(db, response, user)


@router.post("/api/auth/login", response_model=TokenResponse)
async def login(
    body: AuthRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = (
        await db.execute(select(User).where(func.lower(User.email) == body.email))
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return await _issue_tokens(db, response, user)


@router.post("/api/auth/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    neo_refresh: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    if not neo_refresh:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    token_hash = hash_refresh_token(neo_refresh)
    now = datetime.now(UTC)
    token_row = (
        await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
    ).scalar_one_or_none()
    if token_row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = (await db.execute(select(User).where(User.id == token_row.user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    # Rotate refresh token atomically
    token_row.revoked_at = now
    return await _issue_tokens(db, response, user)


@router.post("/api/auth/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    neo_refresh: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> LogoutResponse:
    if neo_refresh:
        token_hash = hash_refresh_token(neo_refresh)
        token_row = (
            await db.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if token_row is not None:
            token_row.revoked_at = datetime.now(UTC)
            await db.commit()

    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/auth")
    return LogoutResponse(ok=True)


@router.get("/api/me", response_model=UserProfileResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserProfileResponse:
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        profile_summary=current_user.profile_summary,
    )
