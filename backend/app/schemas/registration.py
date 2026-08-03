"""Pydantic v2 schemas for the registration API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RegistrationCreate(BaseModel):
    participant_type: Literal["team", "individual"]
    team_id: int | None = None


class RegistrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competition_id: int
    participant_type: str
    team_id: int | None
    user_id: int | None
    status: str
    created_at: datetime
    # 参赛者显示名称（API 层手工填充：队伍=队名，个体=昵称或用户名）。
    participant_name: str | None = None


class MyRegistrationOut(BaseModel):
    """Wrapper for GET /api/my/registrations (avoids ambiguous bare lists)."""

    registrations: list[RegistrationOut]
