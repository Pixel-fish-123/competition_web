"""Pydantic v2 schemas for the team API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=20)


class MemberAddRequest(BaseModel):
    """拉人入队：按 user_id 或 username 指定目标用户，至少提供一个。

    两者都提供时以 user_id 优先（端点内先走 user_id 分支）。
    """

    user_id: int | None = None
    username: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def _require_one_identifier(self) -> "MemberAddRequest":
        if self.user_id is None and self.username is None:
            raise ValueError("user_id 与 username 至少提供一个")
        return self


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    username: str | None
    nickname: str | None
    created_at: datetime


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    captain_id: int
    created_at: datetime
    member_count: int
    members: list[TeamMemberOut] = []
