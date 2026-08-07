"""对局（Match）ORM 模型（todo 14）。

Match 是对局生命周期（pending → in_progress → finished）的持久化载体：

- 对局行由赛程引擎的 schedule 生成（registration → ongoing 状态流转时），
  而非人工创建（Metis C7：不提供 POST /api/matches 创建端点）。
- ``participant_a`` / ``participant_b`` 来自引擎 MatchPlan。单败淘汰的后续
  轮次在排表时参赛者未知，两列为 None，开赛时由引擎根据前序结果解析。
- ``result``（JSON）保存裁判提交的最终结果 {winner, is_draw, score_a,
  score_b}；``result_type`` 为 "win" / "draw" / "abandoned" 冗余标记。
- ``result_locked``：保存结果后锁定，禁止再修改（见 record_match_result）。
- ``gameplay_log``（JSON）保存比赛后从外部 demo 控制器导入的玩法日志
  （事件数组 + 比分 + 胜者，见 api/matches.py 的 gameplay-log 导入端点）。
  仅用于展示，不参与赛程推进；对局结果一律由裁判手工输入（record_match_result）。
- ``engine_match_id`` 是该对局在赛制引擎 schedule 中的全局 match_id
  （引擎按 schedule 迭代顺序从 1 递增分配）。start/record 时按相同
  participants + config 重建引擎，即可用此列定位引擎中的对局并调用
  engine.record_result / 解析后续轮次参赛者（重建是确定性的）。

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
    # 导入的比赛玩法日志（demo 控制器导出）：{"events": [...], "scores":
    # {"defender": X, "attacker": Y}, "winner": "defender"|"attacker"|"draw"|null,
    # "imported_at": "ISO 时间戳"}。仅展示用，不影响赛程引擎。
    gameplay_log: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 保存结果后置 True，结果锁定不可再改（issue 14）。
    result_locked: Mapped[bool] = mapped_column(default=False, nullable=False)
    referee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
