"""TDD tests for the team endpoints (create / add / remove / disband / query).

Multi-user scenarios use a single TestClient whose cookie jar is swapped
between users (register auto-logs-in and sets the "token" cookie).
"""

PASSWORD = "secret123"


def _register(client, username, email):
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"], client.cookies.get("token")


def _as_user(client, token):
    client.cookies.set("token", token)


def _create_team(client, name):
    return client.post("/api/teams", json={"name": name})


def test_create_team_sets_captain_and_first_member(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    _as_user(client, a_token)

    resp = _create_team(client, "队伍A")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "队伍A"
    assert data["captain_id"] == a_id
    assert data["member_count"] == 1
    assert [m["user_id"] for m in data["members"]] == [a_id]


def test_create_team_unauthenticated_returns_401(client):
    resp = _create_team(client, "匿名队")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或登录已失效"


def test_create_team_short_name_returns_422(client):
    _, a_token = _register(client, "user_a", "a@example.com")
    _as_user(client, a_token)
    assert _create_team(client, "A").status_code == 422


def test_add_member_and_full_team(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")
    c_id, c_token = _register(client, "user_c", "c@example.com")
    d_id, d_token = _register(client, "user_d", "d@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]

    resp = client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["member_count"] == 2

    resp = client.post(f"/api/teams/{team_id}/members", json={"user_id": c_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["member_count"] == 3
    assert {m["user_id"] for m in resp.json()["members"]} == {a_id, b_id, c_id}

    # 4th member -> full
    resp = client.post(f"/api/teams/{team_id}/members", json={"user_id": d_id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "队伍已满（最多3人）"


def test_non_captain_cannot_add_member(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")
    e_id, e_token = _register(client, "user_e", "e@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]
    assert client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id}).status_code == 200

    # B (member, not captain) tries to add E
    _as_user(client, b_token)
    resp = client.post(f"/api/teams/{team_id}/members", json={"user_id": e_id})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "只有队长可以添加成员"


def test_member_cannot_create_own_team(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]
    assert client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id}).status_code == 200

    # B already in A's team -> cannot create another team
    _as_user(client, b_token)
    resp = _create_team(client, "队伍B")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "已加入队伍"


def test_free_user_can_create_team(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")
    e_id, e_token = _register(client, "user_e", "e@example.com")

    _as_user(client, a_token)
    team_a = _create_team(client, "队伍A").json()["id"]
    assert client.post(f"/api/teams/{team_a}/members", json={"user_id": b_id}).status_code == 200

    # E has no team -> can create one
    _as_user(client, e_token)
    resp = _create_team(client, "队伍E")
    assert resp.status_code == 200
    assert resp.json()["captain_id"] == e_id


def test_remove_member_frees_user_for_new_team(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]
    assert client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id}).status_code == 200

    resp = client.delete(f"/api/teams/{team_id}/members/{b_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    # B is free now -> creates own team
    _as_user(client, b_token)
    resp = _create_team(client, "队伍B")
    assert resp.status_code == 200
    assert resp.json()["captain_id"] == b_id


def test_captain_cannot_remove_self_then_disband(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]
    assert client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id}).status_code == 200

    resp = client.delete(f"/api/teams/{team_id}/members/{a_id}")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "队长不能退出队伍，请解散或转让"

    resp = client.delete(f"/api/teams/{team_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    resp = client.get("/api/teams/my")
    assert resp.status_code == 200
    assert resp.json() == {"team": None}


def test_my_team_shows_members(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]
    assert client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id}).status_code == 200

    resp = client.get("/api/teams/my")
    assert resp.status_code == 200
    team = resp.json()["team"]
    assert team["id"] == team_id
    assert team["member_count"] == 2
    assert {m["user_id"] for m in team["members"]} == {a_id, b_id}


def test_team_detail_visible_to_any_authenticated_user(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]

    _as_user(client, b_token)  # B is not in the team, but may view it
    resp = client.get(f"/api/teams/{team_id}")
    assert resp.status_code == 200
    assert resp.json()["captain_id"] == a_id
    assert resp.json()["member_count"] == 1


def test_duplicate_team_name_returns_400(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")

    _as_user(client, a_token)
    assert _create_team(client, "同名队").status_code == 200

    _as_user(client, b_token)
    resp = _create_team(client, "同名队")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "队伍名称已存在"


def test_add_member_unknown_team_returns_404(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")

    _as_user(client, a_token)
    resp = client.post("/api/teams/999/members", json={"user_id": b_id})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "队伍不存在"


def test_add_member_unknown_user_returns_404(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]
    resp = client.post(f"/api/teams/{team_id}/members", json={"user_id": 9999})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "用户不存在"


def test_add_member_already_in_other_team_returns_400(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")
    e_id, e_token = _register(client, "user_e", "e@example.com")

    _as_user(client, a_token)
    team_a = _create_team(client, "队伍A").json()["id"]
    assert client.post(f"/api/teams/{team_a}/members", json={"user_id": b_id}).status_code == 200

    # E creates own team, then A tries to recruit E
    _as_user(client, e_token)
    assert _create_team(client, "队伍E").status_code == 200

    _as_user(client, a_token)
    resp = client.post(f"/api/teams/{team_a}/members", json={"user_id": e_id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "该用户已在其他队伍"


def test_remove_member_non_captain_returns_403(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")
    c_id, c_token = _register(client, "user_c", "c@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]
    assert client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id}).status_code == 200
    assert client.post(f"/api/teams/{team_id}/members", json={"user_id": c_id}).status_code == 200

    # B (not captain) tries to remove C
    _as_user(client, b_token)
    resp = client.delete(f"/api/teams/{team_id}/members/{c_id}")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "只有队长可以移除成员"


def test_disband_non_captain_returns_403(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]
    assert client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id}).status_code == 200

    _as_user(client, b_token)
    resp = client.delete(f"/api/teams/{team_id}")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "只有队长可以解散队伍"


def test_disband_removes_team_and_members(client):
    a_id, a_token = _register(client, "user_a", "a@example.com")
    b_id, b_token = _register(client, "user_b", "b@example.com")

    _as_user(client, a_token)
    team_id = _create_team(client, "队伍A").json()["id"]
    assert client.post(f"/api/teams/{team_id}/members", json={"user_id": b_id}).status_code == 200
    assert client.delete(f"/api/teams/{team_id}").status_code == 200

    # Team gone -> 404; B is freed and can join a new team.
    resp = client.get(f"/api/teams/{team_id}")
    assert resp.status_code == 404

    _as_user(client, b_token)
    resp = _create_team(client, "队伍B")
    assert resp.status_code == 200
