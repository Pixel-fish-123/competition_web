"""对局（Match）与玩法会话（GameSession）ORM 模型（todo 14）。

Match 是对局生命周期（pending → in_progress → finished）的持久化载体：

- 对局行由赛程引擎的 schedule 生成（registration → ongoing 状态流转时），
  而非人工创建（Metis C7：不提供 POST /api/matches 创建端点）。
- ``participant_a`` / ``participant_b`` 来自引擎 MatchPlan。单败淘汰的后续
  轮次在排表时参赛者未知，两列为 None，开赛时由引擎根据前序结果解析。
- ``result``（JSON）保存裁判提交的最终结果 {winner, is_draw, score_a,
  score_b}；``result_type`` 为 "win" / "draw" 冗余标记，便于查询过滤。
- ``engine_match_id`` 是该对局在赛制引擎 schedule 中的全局 match_id
  （引擎按 schedule 迭代顺序从 1 递增分配）。start/record 时按相同
  participants + config 重建引擎，即可用此列定位引擎中的对局并调用
  engine.record_result / 解析后续轮次参赛者（重建是确定性的）。

GameSession 是单局玩法会话（一场对局一套玩法，如 triangle_occupy）：

- ``config`` 保存创建会话时的玩法配置（song_lib / seed / sides）。
- ``state_json`` 保存插件 create_session 返回的初始状态 dict，以及后续
  操作后的最新状态（对局中由裁判在玩法路由内更新，todo 14 仅负责落库）。
- ``ended_at`` 由玩法会话结束时回填（本 todo 预留，路由层沿用内存存储）。

表创建策略与其余模型一致：app/main.py import 本模块，
lifespan 的 ``Base.metadata.create_all`` 会建表。
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id"), nullable=False, index=True
    )
    # 引擎中的全局轮次号（1-based，见 RoundPlan.round_number）。
    round_id: Mapped[int] = mapped_column(nullable=False)
    # 单败淘汰后续轮次在排表时参赛者未知 -> 两列均可为 None。
    participant_a: Mapped[int | None] = mapped_column(nullable=True)
    participant_b: Mapped[int | None] = mapped_column(nullable=True)
    # 该对局在赛制引擎 schedule 中的全局 match_id（确定性重建引擎用）。
    engine_match_id: Mapped[int] = mapped_column(nullable=False)
    # "pending" | "in_progress" | "finished"。
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # {"winner": int|None, "is_draw": bool, "score_a": float, "score_b": float}。
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # "win" | "draw"（轮空对局自动记 win，winner=participant_a）。
    result_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    referee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id"), nullable=False, index=True
    )
    # 玩法插件注册表键，如 "triangle_occupy"。
    plugin_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # 创建会话时传入插件的配置（song_lib / seed / sides）。
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    # 插件会话状态 dict（可 JSON 序列化；对局中随操作更新）。
    state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
