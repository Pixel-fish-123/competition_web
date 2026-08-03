"""Pydantic v2 schemas for the auth/user API."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Simple email validation (email-validator package is intentionally NOT
# a dependency; this regex covers the common cases for the competition app).
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    email: str
    password: str = Field(min_length=6, max_length=64)
    nickname: str | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        value = value.strip()
        if len(value) > 120 or not EMAIL_RE.match(value):
            raise ValueError("邮箱格式不正确")
        return value


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPatchRequest(BaseModel):
    """Admin-only partial user update (todo 5): role / status / password.

    All fields optional; ``None`` means "leave unchanged". Password enforces
    the same length policy as RegisterRequest.
    """

    role: str | None = Field(default=None)
    status: str | None = Field(default=None)
    password: str | None = Field(default=None, min_length=6, max_length=64)


class UserMePatchRequest(BaseModel):
    """普通用户修改自己的资料（目前仅昵称）。

    ``None`` 表示不修改该字段；空串会被 min_length=1 拒绝（422）。
    """

    nickname: str | None = Field(default=None, min_length=1, max_length=20)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    nickname: str | None
    role: str
    status: str
    created_at: datetime
