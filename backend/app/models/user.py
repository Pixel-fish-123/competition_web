"""User ORM model.

Table creation strategy (documented):
- app/main.py registers this model by importing it and, in its lifespan,
  calls ``Base.metadata.create_all(bind=engine)`` so tables are created
  automatically on app startup (no alembic in this project yet).
- tests/conftest.py additionally resets tables per test for isolation.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    # 昵称（个人参赛者展示名，可空；旧库升级见 app/main.py 的 _ensure_schema_upgrades）。
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="player", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
