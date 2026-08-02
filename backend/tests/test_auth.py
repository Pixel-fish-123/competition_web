"""TDD tests for the auth endpoints (register / login / me / logout)."""


def _register_payload(username="player1", email="p1@example.com", password="secret123"):
    return {"username": username, "email": email, "password": password}


def test_register_success_sets_cookie_and_returns_userout(client):
    resp = client.post("/api/auth/register", json=_register_payload())
    assert resp.status_code == 200

    data = resp.json()
    assert data["id"] > 0
    assert data["username"] == "player1"
    assert data["email"] == "p1@example.com"
    assert data["role"] == "player"
    assert data["status"] == "active"
    assert isinstance(data["created_at"], str) and data["created_at"]

    set_cookie = resp.headers.get("set-cookie", "")
    assert "token=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


def test_register_duplicate_username_returns_400(client):
    assert client.post("/api/auth/register", json=_register_payload()).status_code == 200
    resp = client.post("/api/auth/register", json=_register_payload(username="player1", email="p2@example.com"))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "用户名已存在"


def test_register_duplicate_email_returns_400(client):
    assert client.post("/api/auth/register", json=_register_payload()).status_code == 200
    resp = client.post("/api/auth/register", json=_register_payload(username="player2", email="p1@example.com"))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "邮箱已被注册"


def test_register_short_password_returns_422(client):
    resp = client.post("/api/auth/register", json=_register_payload(password="12345"))
    assert resp.status_code == 422


def test_register_short_username_returns_422(client):
    resp = client.post("/api/auth/register", json=_register_payload(username="ab"))
    assert resp.status_code == 422


def test_register_invalid_email_returns_422(client):
    resp = client.post("/api/auth/register", json=_register_payload(email="not-an-email"))
    assert resp.status_code == 422


def test_register_does_not_store_plaintext_password(client):
    resp = client.post("/api/auth/register", json=_register_payload())
    assert resp.status_code == 200
    assert "secret123" not in resp.text


def test_login_success_returns_cookie(client):
    assert client.post("/api/auth/register", json=_register_payload()).status_code == 200
    resp = client.post("/api/auth/login", json={"username": "player1", "password": "secret123"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "player1"
    assert "token=" in resp.headers.get("set-cookie", "")


def test_login_wrong_password_returns_401(client):
    assert client.post("/api/auth/register", json=_register_payload()).status_code == 200
    resp = client.post("/api/auth/login", json={"username": "player1", "password": "wrongpass"})
    assert resp.status_code == 401
    assert "token=" not in resp.headers.get("set-cookie", "")


def test_login_unknown_user_returns_401(client):
    resp = client.post("/api/auth/login", json={"username": "nobody", "password": "whatever"})
    assert resp.status_code == 401


def test_me_without_cookie_returns_401(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_invalid_cookie_returns_401(client):
    client.cookies.set("token", "not-a-real-jwt")
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_cookie_returns_user(client):
    client.post("/api/auth/register", json=_register_payload())  # auto-login sets cookie
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "player1"
    assert resp.json()["email"] == "p1@example.com"


def test_logout_clears_cookie_then_me_returns_401(client):
    client.post("/api/auth/register", json=_register_payload())
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    set_cookie = resp.headers.get("set-cookie", "")
    assert "token=" in set_cookie
    assert "max-age=0" in set_cookie.lower()

    me = client.get("/api/auth/me")
    assert me.status_code == 401
