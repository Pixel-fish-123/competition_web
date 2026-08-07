"""TDD tests for AuditLog + admin traffic monitoring endpoints (todo 16)."""

from app.db import SessionLocal
from app.models.audit_log import AuditLog


def _register(client, username="player1", email="p1@example.com", password="secret123"):
    return client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def _audit_rows():
    with SessionLocal() as db:
        return db.query(AuditLog).order_by(AuditLog.id).all()


def test_register_writes_audit_log(client):
    _register(client)
    rows = _audit_rows()
    assert len(rows) == 1
    assert rows[0].action == "register"
    assert rows[0].user_id is not None
    assert rows[0].ip == "testclient"
    assert rows[0].detail == {"username": "player1"}


def test_login_failure_writes_audit_log(client):
    _register(client)
    client.post("/api/auth/login", json={"username": "player1", "password": "wrong"})
    rows = _audit_rows()
    assert [r.action for r in rows] == ["register", "login_failed"]
    failed = rows[1]
    assert failed.user_id is None
    assert failed.ip == "testclient"
    assert failed.detail == {"username": "player1"}


def test_login_success_writes_audit_log(client):
    _register(client)
    client.post("/api/auth/login", json={"username": "player1", "password": "secret123"})
    rows = _audit_rows()
    assert [r.action for r in rows] == ["register", "login"]
    assert rows[1].user_id is not None


def test_admin_traffic_summary_returns_data(client, admin_client):
    _register(client)
    client.post("/api/auth/login", json={"username": "player1", "password": "wrong"})
    client.post("/api/auth/login", json={"username": "player1", "password": "secret123"})

    resp = admin_client.get("/api/admin/traffic/summary")
    assert resp.status_code == 200
    data = resp.json()
    for bucket in ("since_24h", "since_7d"):
        b = data[bucket]
        assert b["failed_logins"] == 1
        assert b["registrations"] >= 1
        assert b["login_attempts"] >= 2
        assert b["actions_by_type"]["login_failed"] == 1
        assert b["actions_by_type"]["login"] == 1


def test_admin_traffic_failed_logins_shows_ip_and_username(client, admin_client):
    _register(client)
    client.post("/api/auth/login", json={"username": "player1", "password": "wrong"})

    resp = admin_client.get("/api/admin/traffic/failed-logins")
    assert resp.status_code == 200
    data = resp.json()
    assert any(item["username"] == "player1" for item in data["top_usernames"])
    assert any(item["ip"] == "testclient" for item in data["top_ips"])


def test_admin_traffic_logs_paginated_and_filterable(client, admin_client):
    _register(client)
    _register(client, username="player2", email="p2@example.com")
    client.post("/api/auth/login", json={"username": "player1", "password": "secret123"})
    # 4 rows: admin_user register (admin_client) + player1/player2 register + player1 login

    resp = admin_client.get("/api/admin/traffic/logs", params={"page": 1, "page_size": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2

    resp2 = admin_client.get("/api/admin/traffic/logs", params={"page": 2, "page_size": 2})
    assert len(resp2.json()["items"]) == 2

    resp3 = admin_client.get("/api/admin/traffic/logs", params={"action": "login"})
    assert resp3.json()["total"] == 1

    resp4 = admin_client.get("/api/admin/traffic/logs", params={"username": "player1"})
    assert resp4.status_code == 200
    assert resp4.json()["total"] == 2  # register(player1) + login(player1)


def test_player_forbidden_from_admin_traffic(client):
    _register(client)
    for path in (
        "/api/admin/traffic/summary",
        "/api/admin/traffic/failed-logins",
        "/api/admin/traffic/logs",
    ):
        assert client.get(path).status_code == 403


def test_unauth_forbidden_from_admin_traffic(client):
    assert client.get("/api/admin/traffic/summary").status_code == 401
