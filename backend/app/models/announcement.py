"""公告（Announcement）ORM 模型（issue 4）。

公告用于在抬头导航向参赛者发布不同时间的文档，支持上传附件
（pdf / word / zip）。附件以内嵌 JSON 列保存元数据，文件本体落在
``backend/uploads/announcements/``（磁盘），下载经 /api/announcements/files/
端点按 stored_name 定位。

表创建策略与其余模型一致：app/main.py import 本模块，
lifespan 的 ``Base.metadata.create_all`` 会建表。
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 附件元数据：{"filename": 原始文件名, "stored_name": 磁盘名(uuid),
    # "size": 字节数, "content_type": MIME}
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    # 发布者（admin）。
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
