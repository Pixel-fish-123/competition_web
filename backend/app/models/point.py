"""PointTransaction ORM model — 双轨积分流水 (todo 17).

每条流水是一次积分的增/减（amount 带符号，±）：

- ``kind`` 三轨之一：
  - "competition"：比赛结束时的自动结算（系统产生，不可人工创建）；
  - "activity"：管理员发放的活动积分；
  - "manual"：管理员手动调整（可正可负，如扣分）。
- ``ref_competition_id``：competition 类流水的来源比赛（可空，用于幂等结算
  检查与按比赛查询）。
- ``reason``：人类可读原因；队伍奖励按 Metis C6/E15 记
  「比赛名次·第N名·队伍<队名>」，个人记「比赛名次·第N名」。
- ``created_by``：操作者 user id（比赛结算记 competition.created_by；
  管理员发放记 admin.id），系统内部操作时也可为 None。

表创建策略与其余模型一致：app/main.py import 本模块，
lifespan 的 ``Base.metadata.create_all`` 会建表。
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PointTransaction(Base):
    __tablename__ = "point_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    # 带符号积分（正=增加，负=扣减）。
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    # "competition" | "activity" | "manual"。
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    ref_competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id"), nullable=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
