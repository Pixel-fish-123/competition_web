"""Competition ORM model: full competition management spec (todo 8).

Fields cover the admin CRUD spec from plan.md §六: banner_url / description
(display), participant_type (who may register), tournament_format + JSON
format_config (赛制: round_robin / swiss / single_elim), points_rule (名次→积分),
gameplay_plugin (玩法模板 registry key, e.g. "triangle_occupy"), song_lib,
referee_ids (裁判组, Metis E3), max_participants, status, time window and
created_by. The status machine (draft → registration → ongoing → finished /
cancelled) is enforced in app/api/competitions.py.

Table creation strategy (same as User/Team): app/main.py imports this module
so ``Base.metadata.create_all`` in the lifespan knows about the table.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    banner_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "team" | "individual" | "mixed" — who may register.
    participant_type: Mapped[str] = mapped_column(String(20), default="mixed", nullable=False)
    # "round_robin" | "swiss" | "single_elim".
    tournament_format: Mapped[str] = mapped_column(String(20), default="round_robin", nullable=False)
    # 赛制配置（组数/轮数/出线/种子…）— free-form JSON consumed by the engine (todo 9-11).
    format_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # 名次→积分配置（名次→积分）— free-form JSON consumed by scoring (todo 12).
    points_rule: Mapped[dict] = mapped_column(JSON, default=dict)
    # 玩法模板插件 registry key, e.g. "triangle_occupy".
    gameplay_plugin: Mapped[str] = mapped_column(String(50), default="triangle_occupy", nullable=False)
    song_lib: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 裁判组 (Metis E3): user ids whose role is "referee" — validated in the API.
    referee_ids: Mapped[list] = mapped_column(JSON, default=list)
    max_participants: Mapped[int] = mapped_column(default=50, nullable=False)
    # "draft" | "registration" | "ongoing" | "finished" | "cancelled".
    # Registration is only allowed while status == "registration" (see registrations API).
    status: Mapped[str] = mapped_column(String(20), default="registration", nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Admin who created the competition (set by POST /api/competitions).
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
