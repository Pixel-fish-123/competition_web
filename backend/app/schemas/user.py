"""Pydantic v2 schemas for the auth/user API."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Simple email validation (email-validator package is intentionally NOT
# a dependency; this regex covers the common cases for the competition app).
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=30)
    email: str
    password: str = Field(min_length=6, max_length=64)
    nickname: str | None = Field(default=None, min_length=2, max_length=30)
    qq: str | None = Field(default=None, max_length=20)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        value = value.strip()
        if len(value) > 120 or not EMAIL_RE.match(value):
            raise ValueError("邮箱格式不正确")
        return value

    @field_validator("qq")
    @classmethod
    def _validate_qq(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not value.isdigit() or len(value) > 20:
            raise ValueError("QQ 号应为纯数字")
        return value


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPatchRequest(BaseModel):
    """Admin-only partial user update (todo 5): role / password.

    All fields optional; ``None`` means "leave unchanged". Password enforces
    the same length policy as RegisterRequest. ``status``（封禁）已随
    issue 4 删除：账号状态由系统管理，不再提供人工封禁。
    """

    role: str | None = Field(default=None)
    password: str | None = Field(default=None, min_length=6, max_length=64)
    qq: str | None = Field(default=None, max_length=20)

    @field_validator("qq")
    @classmethod
    def _validate_qq(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return ""  # 空串 = 清除 QQ（与个人资料修改一致）
        if not value.isdigit() or len(value) > 20:
            raise ValueError("QQ 号应为纯数字")
        return value


class UserMePatchRequest(BaseModel):
    """普通用户修改自己的资料（昵称 / QQ）。

    ``None`` 表示不修改该字段；空串会被 min_length=1 拒绝（422）。
    """

    nickname: str | None = Field(default=None, min_length=2, max_length=30)
    qq: str | None = Field(default=None, max_length=20)

    @field_validator("qq")
    @classmethod
    def _validate_qq(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return ""  # 空串 = 清除 QQ
        if not value.isdigit() or len(value) > 20:
            raise ValueError("QQ 号应为纯数字")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    nickname: str | None
    qq: str | None
    role: str
    status: str
    created_at: datetime
