"""Pydantic v2 schemas for the team API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=20)


class MemberAddRequest(BaseModel):
    user_id: int


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    captain_id: int
    created_at: datetime
    member_count: int
    members: list[TeamMemberOut] = []
