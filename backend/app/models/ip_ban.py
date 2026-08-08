"""IP 黑名单 ORM 模型（恶意登录防护）。

每个被拉黑的 IP 一行：自动拉黑（24h 内失败登录 ≥20 次）或后台手动添加。
表由 lifespan 的 ``Base.metadata.create_all`` 自动创建；内存集合由
``core/ip_ban.load_blacklist`` 在启动时从本表加载。
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IpBan(Base):
    __tablename__ = "ip_bans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    # 手动添加时为 admin 的 id；自动拉黑为 None。
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
