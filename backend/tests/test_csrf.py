"""TDD tests for CSRF middleware: cross-site state-changing requests are
rejected with 403 unless Origin is same-site or explicitly allowed."""

REGISTER = {
    "username": "csrf_user",
    "email": "csrf@example.com",
    "password": "secret123",
}


def test_post_with_forged_origin_rejected_403(client):
    resp = client.post("/api/auth/register", json=REGISTER, headers={"Origin": "http://evil.com"})
    assert resp.status_code == 403


def test_post_with_no_origin_allowed(client):
    resp = client.post("/api/auth/register", json=REGISTER)
    assert resp.status_code == 200


def test_post_with_same_origin_allowed(client):
    # TestClient default base_url is http://testserver -> same-site Origin.
    resp = client.post("/api/auth/register", json=REGISTER, headers={"Origin": "http://testserver"})
    assert resp.status_code == 200


def test_post_with_allowed_localhost_origin_allowed(client):
    resp = client.post(
        "/api/auth/register",
        json=REGISTER,
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200


def test_post_with_allowed_127_origin_allowed(client):
    resp = client.post(
        "/api/auth/register",
        json=REGISTER,
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert resp.status_code == 200


def test_get_with_forged_origin_not_blocked(client):
    # CSRF only guards non-safe methods.
    resp = client.get("/api/health", headers={"Origin": "http://evil.com"})
    assert resp.status_code == 200
