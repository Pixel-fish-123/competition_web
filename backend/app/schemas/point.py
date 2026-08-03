"""Pydantic v2 schemas for the points / leaderboard API (todo 17)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PointTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    amount: float
    kind: str
    ref_competition_id: int | None
    reason: str
    created_by: int | None
    created_at: datetime


class MyPointsOut(BaseModel):
    """GET /api/points/me: 我的流水（最新在前）+ 当前余额（总流水求和）。"""

    transactions: list[PointTransactionOut]
    balance: float


class LeaderboardRow(BaseModel):
    """全局榜一行：按用户聚合。total = 该用户全部流水之和（主列）。

    competition_sum / activity_sum 是 total 的两个维度分量（manual 计入
    total 但不单列），保留仅为向后兼容 —— 前端已合并为单一 total 列，
    不再使用分列。
    """

    user_id: int
    username: str
    total: float
    competition_sum: float | None = None
    activity_sum: float | None = None


class PointsGrantIn(BaseModel):
    """管理员发放活动/手动积分。competition 类只能由系统结算产生。"""

    user_id: int
    amount: float
    kind: Literal["activity", "manual"]
    reason: str = Field(min_length=2, max_length=255)
