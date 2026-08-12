"""赛程只读接口的 Pydantic schema（机器人/插件拉取对局名单用）。"""

from pydantic import BaseModel, ConfigDict


class ScheduleParticipant(BaseModel):
    """参赛单位：个体（个人赛）或队伍（团队赛）。

    - ``id``：参赛单位 id（个体=用户 id；队伍=队伍 id），与对局里的
      participant_a / participant_b 一致，供前端定位胜者、跳转详情。
    - ``name``：个体=昵称或用户名；队伍=队名。
    - ``qqs``：个体为该用户 QQ（未填时为空列表）；队伍为全部成员 QQ。
    """

    id: int | None = None
    type: str  # "individual" | "team"
    name: str | None = None
    qqs: list[str] = []


class ScheduleMatch(BaseModel):
    """单局对局（含双方身份与 QQ，供 bot 在群里 @ 选手）。"""

    id: int
    round_id: int
    status: str  # "pending" | "in_progress" | "finished"
    result_type: str | None = None
    result: dict | None = None
    participant_a: ScheduleParticipant | None = None
    participant_b: ScheduleParticipant | None = None


class ScheduleCompetition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    tournament_format: str


class ScheduleOut(BaseModel):
    competition: ScheduleCompetition
    matches: list[ScheduleMatch]
