"""Pydantic v2 schemas for the competition management API (todo 8)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompetitionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = None
    banner_url: str | None = None
    participant_type: Literal["individual", "mixed"] = "mixed"
    tournament_format: Literal["swiss", "single_elim"] = "swiss"
    format_config: dict = Field(default_factory=dict)
    referee_ids: list[int] = Field(default_factory=list)
    max_participants: int = Field(default=50, ge=1)
    start_time: datetime | None = None
    end_time: datetime | None = None


class CompetitionUpdate(BaseModel):
    """Admin partial update — every field optional; absent means "unchanged"."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = None
    banner_url: str | None = None
    participant_type: Literal["individual", "mixed"] | None = None
    tournament_format: Literal["swiss", "single_elim"] | None = None
    format_config: dict | None = None
    referee_ids: list[int] | None = None
    max_participants: int | None = Field(default=None, ge=1)
    start_time: datetime | None = None
    end_time: datetime | None = None


class CompetitionStatusUpdate(BaseModel):
    """Status-machine transition target (validated against the transition table).

    ``force``：true 时强制结束（issue 8）——未完成对局标记为作废
    (abandoned)，不参与排名，比赛直接进入 finished。
    """

    status: Literal["draft", "registration", "ongoing", "finished", "cancelled"]
    force: bool = False


class CompetitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    banner_url: str | None
    description: str | None
    participant_type: str
    tournament_format: str
    format_config: dict
    referee_ids: list[int]
    max_participants: int
    status: str
    start_time: datetime | None
    end_time: datetime | None
    created_by: int
    created_at: datetime
