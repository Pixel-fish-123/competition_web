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


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: str
    status: str
    created_at: datetime
