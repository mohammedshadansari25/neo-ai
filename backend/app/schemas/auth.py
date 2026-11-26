import uuid

from pydantic import BaseModel, Field, field_validator


class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or "." not in cleaned.split("@")[-1]:
            raise ValueError("Invalid email address")
        return cleaned


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    profile_summary: dict[str, object]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileResponse


class LogoutResponse(BaseModel):
    ok: bool = True
