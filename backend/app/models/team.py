"""Team and TeamMember ORM models.

A competition team has exactly one captain and at most 3 members (including
the captain). A user can belong to at most one team — enforced by the unique
constraint on ``team_members.user_id``.

Table creation strategy (same as User): app/main.py imports this module so
``Base.metadata.create_all`` in the lifespan knows about the tables.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    captain_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id"), nullable=False, index=True
    )
    # A user can belong to at most ONE team (unique constraint).
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
