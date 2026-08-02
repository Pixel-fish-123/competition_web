"""RBAC dependencies: current-user resolution + role gate (todo 5).

- ``get_current_user``: reads the httpOnly "token" cookie, decodes the JWT,
  loads the User from the DB, and rejects missing / banned accounts. The
  JWT's role claim is NOT trusted for authorization — the live DB role is.
- ``require_role(*roles)``: dependency factory that gates on ``user.role``.
  Convenience instances: ``require_admin``, ``require_referee``.
"""

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import get_db
from app.models.user import User

COOKIE_NAME = "token"

UNAUTHORIZED_DETAIL = "未登录或登录已失效"
FORBIDDEN_DETAIL = "权限不足"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the authenticated user from the "token" cookie, or 401.

    401 (detail "未登录或登录已失效") when: no cookie, undecodable/expired
    JWT, unknown user id, or the account is not active (e.g. banned).
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)
    try:
        payload = decode_access_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)

    user = db.get(User, user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)
    return user


def require_role(*roles: str):
    """Dependency factory: allow only users whose role is in ``roles``.

    Roles: "admin", "referee", "player". Returns the resolved user so
    endpoints can use it (e.g. for self/ownership checks).
    """

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail=FORBIDDEN_DETAIL)
        return current_user

    return dependency


require_admin = require_role("admin")
require_referee = require_role("admin", "referee")
