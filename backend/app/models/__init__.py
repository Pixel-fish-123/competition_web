"""ORM model registry. Importing this package registers every table on
``Base.metadata`` so app/main.py's lifespan ``create_all`` builds them all."""

from app.models.audit_log import AuditLog
from app.models.competition import Competition
from app.models.match import Match
from app.models.point import PointTransaction
from app.models.registration import Registration
from app.models.team import Team, TeamMember
from app.models.user import User

__all__ = [
    "User",
    "Team",
    "TeamMember",
    "Competition",
    "Registration",
    "Match",
    "AuditLog",
    "PointTransaction",
]
