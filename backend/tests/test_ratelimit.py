"""TDD tests for brute-force account lockout + slowapi rate limits (todo 16).

Metis C2: lockout threshold is uniformly 5 consecutive failures (not 6).
The 6th attempt — even with the CORRECT password — must be rejected with 423.
"""

from app.core import lockout


def _register(client, username="player1", email="p1@example.com", password="secret123"):
    return client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def _wrong_logins(client, username, count=5, password="wrongpass"):
    codes = []
    for _ in range(count):
        resp = client.post("/api/auth/login", json={"username": username, "password": password})
        codes.append(resp.status_code)
    return codes


def test_five_failed_logins_lock_account_sixth_correct_gets_423(client):
    _register(client)
    assert _wrong_logins(client, "player1", 5) == [401] * 5

    resp = client.post("/api/auth/login", json={"username": "player1", "password": "secret123"})
    assert resp.status_code == 423
    assert "账号已锁定" in resp.json()["detail"]


def test_unknown_user_failures_also_lock_and_423(client):
    # Dual dimension: lockout applies to the attempted username even if it
    # does not exist in the DB (prevents username-enumeration-by-lockout).
    _wrong_logins(client, "ghost", 5)
    resp = client.post("/api/auth/login", json={"username": "ghost", "password": "whatever"})
    assert resp.status_code == 423


def test_lockout_expires_after_timeout(client, monkeypatch):
    monkeypatch.setattr(lockout, "LOCKOUT_SECONDS", 0)
    _register(client)
    _wrong_logins(client, "player1", 5)

    # Lock duration is 0 → the lock has already expired; the correct password
    # must now succeed again.
    resp = client.post("/api/auth/login", json={"username": "player1", "password": "secret123"})
    assert resp.status_code == 200


def test_successful_login_resets_failure_count(client):
    _register(client)
    _wrong_logins(client, "player1", 3)  # not enough to lock
    resp = client.post("/api/auth/login", json={"username": "player1", "password": "secret123"})
    assert resp.status_code == 200

    # Failures again but reset stays: 3 more failures then correct still works
    # (total consecutive failures after success is 3, below 5).
    _wrong_logins(client, "player1", 3)
    resp = client.post("/api/auth/login", json={"username": "player1", "password": "secret123"})
    assert resp.status_code == 200


def test_login_rate_limit_returns_429(client):
    statuses = []
    for i in range(15):
        resp = client.post("/api/auth/login", json={"username": f"user{i}", "password": "wrong"})
        statuses.append(resp.status_code)
    assert 429 in statuses

    resp = client.post("/api/auth/login", json={"username": "fresh", "password": "x"})
    assert resp.status_code == 429
    assert resp.json()["detail"] == "请求过于频繁，请稍后再试"
