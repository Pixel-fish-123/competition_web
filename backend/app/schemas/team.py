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


class AdminTeamCreate(BaseModel):
    """后台建队（自定义团队）：队长 + 成员名单（≤3 人，队长必在成员内）。"""

    name: str = Field(min_length=2, max_length=20)
    captain_id: int
    member_ids: list[int] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def _captain_must_be_member(self) -> "AdminTeamCreate":
        if self.captain_id not in self.member_ids:
            raise ValueError("队长必须包含在成员名单中")
        if len(set(self.member_ids)) != len(self.member_ids):
            raise ValueError("成员名单不能重复")
        return self


class AdminTeamUpdate(BaseModel):
    """后台修改队伍：全部可选；有报名记录的队伍仅允许改名。"""

    name: str | None = Field(default=None, min_length=2, max_length=20)
    captain_id: int | None = None
    member_ids: list[int] | None = Field(default=None, min_length=1, max_length=3)

    @model_validator(mode="after")
    def _member_rules(self) -> "AdminTeamUpdate":
        if self.member_ids is not None:
            if len(set(self.member_ids)) != len(self.member_ids):
                raise ValueError("成员名单不能重复")
            if self.captain_id is not None and self.captain_id not in self.member_ids:
                raise ValueError("队长必须包含在成员名单中")
        return self
