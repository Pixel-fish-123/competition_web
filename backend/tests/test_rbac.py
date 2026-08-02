"""TDD tests for the RBAC system (todo 5): dependencies + admin user management."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.rbac import get_current_user, require_admin, require_referee
from app.db import SessionLocal
from app.main import app
from app.models.user import User

PASSWORD = "secret123"

ADMIN_USERNAME = "admin_user"


# ---------------------------------------------------------------------------
# helpers — each user gets its own TestClient (isolated cookie jar)
# ---------------------------------------------------------------------------


def _register_user(username, email):
    """Register via a throwaway client (jar discarded) and return the UserOut."""
    c = TestClient(app)
    resp = c.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 200
    return resp.json()


def _login_client(username, password=PASSWORD):
    """A fresh TestClient logged in as username."""
    c = TestClient(app)
    resp = c.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return c


def _user_id(admin_client, username):
    listing = admin_client.get("/api/admin/users").json()
    return next(u["id"] for u in listing if u["username"] == username)


def _call_get_current_user(token):
    """Invoke the get_current_user dependency directly (unit-level)."""
    headers = []
    if token is not None:
        headers = [(b"cookie", f"token={token}".encode())]
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    db = SessionLocal()
    try:
        return get_current_user(request, db)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RBAC dependency: get_current_user
# ---------------------------------------------------------------------------


def test_get_current_user_no_token_401():
    with pytest.raises(HTTPException) as ei:
        _call_get_current_user(None)
    assert ei.value.status_code == 401
    assert ei.value.detail == "未登录或登录已失效"


def test_get_current_user_invalid_token_401():
    with pytest.raises(HTTPException) as ei:
        _call_get_current_user("not-a-real-jwt")
    assert ei.value.status_code == 401
    assert ei.value.detail == "未登录或登录已失效"


def test_get_current_user_returns_active_user(client):
    _register_user("player1", "p1@example.com")
    user = _call_get_current_user(_login_client("player1").cookies.get("token"))
    assert user.username == "player1"
    assert user.role == "player"
    assert user.status == "active"


def test_get_current_user_rejects_banned_user(admin_client):
    _register_user("player1", "p1@example.com")
    pid = _user_id(admin_client, "player1")
    assert admin_client.patch(f"/api/admin/users/{pid}", json={"status": "banned"}).status_code == 200

    with pytest.raises(HTTPException) as ei:
        _call_get_current_user(_login_client("player1").cookies.get("token"))
    assert ei.value.status_code == 401
    assert ei.value.detail == "未登录或登录已失效"


# ---------------------------------------------------------------------------
# require_role factory
# ---------------------------------------------------------------------------


def _user(role):
    return User(
        id=1,
        username="u",
        email="u@example.com",
        password_hash="x",
        role=role,
        status="active",
    )


def test_require_referee_allows_admin_and_referee():
    assert require_referee(current_user=_user("admin")).role == "admin"
    assert require_referee(current_user=_user("referee")).role == "referee"


def test_require_referee_rejects_player():
    with pytest.raises(HTTPException) as ei:
        require_referee(current_user=_user("player"))
    assert ei.value.status_code == 403
    assert ei.value.detail == "权限不足"


def test_require_admin_rejects_referee_and_player():
    for role in ("referee", "player"):
        with pytest.raises(HTTPException) as ei:
            require_admin(current_user=_user(role))
        assert ei.value.status_code == 403
        assert ei.value.detail == "权限不足"


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------


def test_unauthenticated_admin_users_401(client):
    resp = client.get("/api/admin/users")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或登录已失效"


def test_player_admin_users_403(client):
    _register_user("player1", "p1@example.com")
    resp = _login_client("player1").get("/api/admin/users")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "权限不足"


def test_admin_lists_all_users_ordered_by_id(admin_client):
    _register_user("player1", "p1@example.com")
    _register_user("player2", "p2@example.com")

    resp = admin_client.get("/api/admin/users")
    assert resp.status_code == 200
    data = resp.json()
    assert [u["username"] for u in data] == [ADMIN_USERNAME, "player1", "player2"]
    assert [u["id"] for u in data] == sorted(u["id"] for u in data)
    for u in data:
        assert {"id", "username", "email", "role", "status", "created_at"} <= set(u)


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/{user_id}
# ---------------------------------------------------------------------------


def test_admin_promotes_user_to_referee(admin_client):
    _register_user("player1", "p1@example.com")
    pid = _user_id(admin_client, "player1")

    resp = admin_client.patch(f"/api/admin/users/{pid}", json={"role": "referee"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "referee"

    # persisted — visible in the admin list
    listing = admin_client.get("/api/admin/users").json()
    assert next(u for u in listing if u["username"] == "player1")["role"] == "referee"

    # re-login as the referee: /me reflects the new role
    referee_client = _login_client("player1")
    me = referee_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "referee"

    # referee must NOT access admin endpoints (role separation)
    resp = referee_client.get("/api/admin/users")
    assert resp.status_code == 403


def test_admin_bans_user(admin_client):
    _register_user("player1", "p1@example.com")
    pid = _user_id(admin_client, "player1")

    resp = admin_client.patch(f"/api/admin/users/{pid}", json={"status": "banned"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "banned"

    # banned user is rejected by get_current_user (401, not 403)
    banned_client = _login_client("player1")
    resp = banned_client.get("/api/admin/users")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或登录已失效"


def test_admin_resets_user_password(admin_client):
    _register_user("player1", "p1@example.com")
    pid = _user_id(admin_client, "player1")

    resp = admin_client.patch(f"/api/admin/users/{pid}", json={"password": "newpass123"})
    assert resp.status_code == 200

    # old password no longer works
    old = TestClient(app)
    resp = old.post("/api/auth/login", json={"username": "player1", "password": PASSWORD})
    assert resp.status_code == 401

    # new password works
    new = _login_client("player1", password="newpass123")
    assert new.get("/api/auth/me").json()["username"] == "player1"


def test_admin_cannot_demote_last_admin(admin_client):
    # admin_client is the ONLY admin in this fresh DB
    admin_id = _user_id(admin_client, ADMIN_USERNAME)

    resp = admin_client.patch(f"/api/admin/users/{admin_id}", json={"role": "player"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "不能降级最后一个管理员"

    # role unchanged
    listing = admin_client.get("/api/admin/users").json()
    assert next(u for u in listing if u["username"] == ADMIN_USERNAME)["role"] == "admin"


def test_admin_can_demote_self_when_another_admin_exists(admin_client):
    _register_user("player1", "p1@example.com")
    pid = _user_id(admin_client, "player1")
    assert admin_client.patch(f"/api/admin/users/{pid}", json={"role": "admin"}).status_code == 200

    admin_id = _user_id(admin_client, ADMIN_USERNAME)
    resp = admin_client.patch(f"/api/admin/users/{admin_id}", json={"role": "referee"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "referee"


def test_admin_patch_invalid_role_400(admin_client):
    pid = _user_id(admin_client, ADMIN_USERNAME)
    resp = admin_client.patch(f"/api/admin/users/{pid}", json={"role": "superadmin"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "无效的角色"


def test_admin_patch_invalid_status_400(admin_client):
    pid = _user_id(admin_client, ADMIN_USERNAME)
    resp = admin_client.patch(f"/api/admin/users/{pid}", json={"status": "ghost"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "无效的状态"


def test_admin_patch_short_password_422(admin_client):
    pid = _user_id(admin_client, ADMIN_USERNAME)
    resp = admin_client.patch(f"/api/admin/users/{pid}", json={"password": "123"})
    assert resp.status_code == 422


def test_admin_patch_unknown_user_404(admin_client):
    resp = admin_client.patch("/api/admin/users/9999", json={"role": "referee"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "用户不存在"
