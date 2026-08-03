"""TDD tests for 昵称功能（bug C 回归）。

- 注册可携带 nickname，UserOut 回显。
- 普通用户 PATCH /api/auth/me 修改自己的昵称；GET /api/auth/me 反映更新。
- 空串昵称 422；未登录 PATCH 401。
"""

PASSWORD = "secret123"


def _register(client, username, email, nickname=None):
    client.cookies.clear()
    payload = {"username": username, "email": email, "password": PASSWORD}
    if nickname is not None:
        payload["nickname"] = nickname
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json(), client.cookies.get("token")


def test_register_with_nickname_echoes_in_userout(client):
    data, token = _register(client, "nick_user", "nick@example.com", nickname="小萌")
    assert data["nickname"] == "小萌"
    # 无昵称注册 -> None 回显。
    data2, _ = _register(client, "no_nick", "nonick@example.com")
    assert data2["nickname"] is None


def test_patch_me_updates_nickname(client):
    _, token = _register(client, "nick_patch", "nickpatch@example.com")
    client.cookies.set("token", token)

    resp = client.patch("/api/auth/me", json={"nickname": "新昵称"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["nickname"] == "新昵称"

    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["nickname"] == "新昵称"


def test_patch_me_empty_nickname_returns_422(client):
    _, token = _register(client, "nick_empty", "nickempty@example.com")
    client.cookies.set("token", token)

    resp = client.patch("/api/auth/me", json={"nickname": ""})
    assert resp.status_code == 422


def test_patch_me_unauthenticated_returns_401(client):
    resp = client.patch("/api/auth/me", json={"nickname": "路人"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或登录已失效"


def test_register_nickname_too_long_returns_422(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "nick_long",
            "email": "nicklong@example.com",
            "password": PASSWORD,
            "nickname": "x" * 21,
        },
    )
    assert resp.status_code == 422
