"""Minimal placeholder Competition ORM model (todo 7 scope only).

Deliberately MINIMAL: only the fields registrations need (id, name,
participant_type, max_participants, status, created_at). Full competition
management (format_config / points_rule / referee_ids / admin CRUD) is owned
by todo 8 and must NOT be added here.

Table creation strategy (same as User/Team): app/main.py imports this module
so ``Base.metadata.create_all`` in the lifespan knows about the table.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # "mixed" | "team" | "individual" — used later by the admin UI (todo 8).
    participant_type: Mapped[str] = mapped_column(String(20), default="mixed", nullable=False)
    max_participants: Mapped[int] = mapped_column(default=50, nullable=False)
    # "registration" | "ongoing" | "finished" — registration allowed while "registration".
    status: Mapped[str] = mapped_column(String(20), default="registration", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
