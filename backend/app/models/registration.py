"""Registration ORM model: one row per competition participant unit.

- Individual registration: ``user_id`` = the registering user, ``team_id`` None.
- Team registration: the team registers as a unit — ``user_id`` = the CAPTAIN's
  id (team members are covered via team membership), ``team_id`` = the team.

The unique constraint ``uq_reg_competition_user`` makes it structurally
impossible for the same user (or captain) to register twice for the same
competition; the team+competition uniqueness is enforced in the endpoint
(team_id is nullable, so SQLite's "NULLs are distinct" semantics would let
duplicate team rows through a naive unique index).

Table creation strategy (same as User/Team): app/main.py imports this module
so ``Base.metadata.create_all`` in the lifespan knows about the table.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (
        # One user cannot register twice for the same competition at the
        # participant level (for team registrations user_id is the captain's).
        UniqueConstraint("competition_id", "user_id", name="uq_reg_competition_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id"), nullable=False, index=True
    )
    # "team" | "individual"
    participant_type: Mapped[str] = mapped_column(String(20), nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # "pending" | "approved" | "rejected" — approval flows come with admin (todo 8/19).
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    approved_by: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
