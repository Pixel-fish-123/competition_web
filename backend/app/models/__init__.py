"""ORM model registry. Importing this package registers every table on
``Base.metadata`` so app/main.py's lifespan ``create_all`` builds them all."""

from app.models.team import Team, TeamMember
from app.models.user import User

__all__ = ["User", "Team", "TeamMember"]
