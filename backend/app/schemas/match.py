"""Pydantic v2 schemas for the match / gameplay-session API (todo 14)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MatchResultIn(BaseModel):
    """裁判提交的最终对局结果。

    - ``is_draw`` 为 True 时 ``winner`` 必须为 None（引擎侧校验）。
    - ``score_a`` / ``score_b`` 供净胜分（net_score）决胜使用。
    - ``lock``：true 时保存结果并锁定（issue 14）——锁定后结果不可再修改。
    """

    winner: int | None = None
    is_draw: bool = False
    score_a: float = 0.0
    score_b: float = 0.0
    lock: bool = False


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
    # 导入的比赛玩法日志（demo 控制器导出，见 gameplay-log 导入端点）。
    gameplay_log: dict | None = None
    # 结果是否已锁定（保存结果后不可再改，issue 14）。
    result_locked: bool = False
    referee_id: int | None
    scheduled_at: datetime | None
    created_at: datetime
    # 参赛者显示名称（API 层手工填充，不依赖 from_attributes：
    # 队伍=队名，个体=昵称或用户名）。
    participant_a_name: str | None = None
    participant_b_name: str | None = None


class MatchDetailOut(BaseModel):
    """单局详情：对局信息 + 已导入的玩法日志（在 match.gameplay_log 内）。"""

    match: MatchOut
