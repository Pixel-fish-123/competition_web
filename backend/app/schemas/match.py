"""Pydantic v2 schemas for the match / gameplay-session API (todo 14)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MatchResultIn(BaseModel):
    """裁判提交的最终对局结果。

    - ``is_draw`` 为 True 时 ``winner`` 必须为 None（引擎侧校验）。
    - ``score_a`` / ``score_b`` 供净胜分（net_score）决胜使用。
    """

    winner: int | None = None
    is_draw: bool = False
    score_a: float = 0.0
    score_b: float = 0.0


class MatchStartIn(BaseModel):
    """开赛可选参数（scheduled_at 预留排期展示）。"""

    scheduled_at: datetime | None = None


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competition_id: int
    round_id: int
    participant_a: int | None
    participant_b: int | None
    status: str
    result: dict | None
    result_type: str | None
    referee_id: int | None
    scheduled_at: datetime | None
    created_at: datetime


class GameSessionOut(BaseModel):
    """玩法会话详情（state = state_json 的公开视图）。"""

    id: int
    match_id: int
    plugin_name: str
    state: dict | None
    started_at: datetime | None
    ended_at: datetime | None


class MatchDetailOut(BaseModel):
    """单局详情：对局信息 + 该局的玩法会话（若已开赛）。"""

    match: MatchOut
    session: GameSessionOut | None
