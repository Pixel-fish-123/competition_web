"""后台团队管理测试（需求 2）：建队 / 改成员 / 改名 / 删除 + 约束。

约束（用户确认）：
- 有报名记录的队伍：仅允许改名；改成员/队长 400；删除 400。
- 队长必须在成员名单内（≤3 人）；用户全局唯一属于一支队伍。
- 无报名记录的队伍可完全编辑 / 删除。
"""

from app.db import SessionLocal
from app.models.registration import Registration
from app.models.user import User

PASSWORD = "secret123"

BASE_PAYLOAD = {
    "name": "团队测试比赛",
    "participant_type": "mixed",
    "tournament_format": "swiss",
    "referee_ids": [],
    "max_participants": 10,
}


def _register(client, username, email):
    client.cookies.clear()
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _team_payload(captain_id, member_ids, name="测试战队"):
    return {"name": name, "captain_id": captain_id, "member_ids": member_ids}


def _create_team(admin_client, payload):
    resp = admin_client.post("/api/admin/teams", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _register_team_to_competition(admin_client, team_id, captain_id):
    """建比赛 -> registration 状态 -> 队长报名队伍（pending 即算有报名）。"""
    admin_token = admin_client.cookies.get("token")
    comp_resp = admin_client.post("/api/competitions", json=BASE_PAYLOAD)
    assert comp_resp.status_code == 200, comp_resp.text
    comp_id = comp_resp.json()["id"]
    assert (
        admin_client.post(f"/api/competitions/{comp_id}/status", json={"status": "registration"}).status_code
        == 200
    )
    with SessionLocal() as db:
        captain = db.get(User, captain_id)
        db.commit()
    _as_user(admin_client, admin_token)  # 保持 admin 身份
    # 用 admin 代理队长无法直接调用（需队长 cookie），直接插报名行。
    with SessionLocal() as db:
        db.add(
            Registration(
                competition_id=comp_id,
                participant_type="team",
                team_id=team_id,
                user_id=captain_id,
                status="pending",
            )
        )
        db.commit()
    return comp_id


def _as_user(client, token):
    client.cookies.clear()
    client.cookies.set("token", token)


def test_admin_teams_list_create(admin_client, client):
    a_id = _register(client, "team_a", "team_a@example.com")
    b_id = _register(client, "team_b", "team_b@example.com")
    rows = admin_client.get("/api/admin/teams").json()
    assert rows == []

    team = _create_team(admin_client, _team_payload(a_id, [a_id, b_id]))
    assert team["name"] == "测试战队"
    assert team["captain_id"] == a_id
    assert team["member_count"] == 2
    assert team["has_registrations"] is False
    assert {m["user_id"] for m in team["members"]} == {a_id, b_id}

    rows = admin_client.get("/api/admin/teams").json()
    assert len(rows) == 1
    assert rows[0]["captain_username"] == "team_a"


def test_admin_create_team_validation(admin_client, client):
    a_id = _register(client, "team_c", "team_c@example.com")
    b_id = _register(client, "team_d", "team_d@example.com")
    c_id = _register(client, "team_e", "team_e@example.com")

    # 队长不在成员名单 -> 422。
    resp = admin_client.post(
        "/api/admin/teams", json=_team_payload(a_id, [b_id, c_id])
    )
    assert resp.status_code == 422

    # 队名重复 -> 400。
    _create_team(admin_client, _team_payload(a_id, [a_id, b_id], name="同名队"))
    resp = admin_client.post(
        "/api/admin/teams", json=_team_payload(c_id, [c_id], name="同名队")
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "队伍名称已存在"

    # 用户已在其他队伍 -> 400。
    resp = admin_client.post(
        "/api/admin/teams", json=_team_payload(b_id, [b_id, a_id], name="新队伍")
    )
    assert resp.status_code == 400
    assert "已在其他队伍" in resp.json()["detail"]

    # 成员超过 3 人 -> 422。
    resp = admin_client.post(
        "/api/admin/teams",
        json={
            "name": "四人队",
            "captain_id": a_id,
            "member_ids": [a_id, b_id, c_id, 999],
        },
    )
    assert resp.status_code == 422


def test_admin_update_team_members_and_captain(admin_client, client):
    a_id = _register(client, "team_f", "team_f@example.com")
    b_id = _register(client, "team_g", "team_g@example.com")
    c_id = _register(client, "team_h", "team_h@example.com")

    team = _create_team(admin_client, _team_payload(a_id, [a_id, b_id]))

    # 改队长 + 换成员（b 出，c 进，队长 a -> c）。
    resp = admin_client.patch(
        f"/api/admin/teams/{team['id']}",
        json={"captain_id": c_id, "member_ids": [c_id, a_id]},
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["captain_id"] == c_id
    assert {m["user_id"] for m in updated["members"]} == {c_id, a_id}

    # 仅改名。
    resp = admin_client.patch(f"/api/admin/teams/{team['id']}", json={"name": "改名队"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "改名队"

    # 队长不在新成员名单 -> 422。
    resp = admin_client.patch(
        f"/api/admin/teams/{team['id']}",
        json={"captain_id": c_id, "member_ids": [a_id]},
    )
    assert resp.status_code == 422


def test_admin_team_with_registrations_restricted(admin_client, client):
    a_id = _register(client, "team_i", "team_i@example.com")
    b_id = _register(client, "team_j", "team_j@example.com")
    team = _create_team(admin_client, _team_payload(a_id, [a_id, b_id]))
    _register_team_to_competition(admin_client, team["id"], a_id)

    # 有报名：只许改名。
    resp = admin_client.patch(
        f"/api/admin/teams/{team['id']}", json={"name": "报名后改名"}
    )
    assert resp.status_code == 200
    assert resp.json()["has_registrations"] is True

    # 有报名：改成员/队长 -> 400。
    resp = admin_client.patch(
        f"/api/admin/teams/{team['id']}", json={"member_ids": [a_id]}
    )
    assert resp.status_code == 400
    assert "只能修改队伍名称" in resp.json()["detail"]
    resp = admin_client.patch(
        f"/api/admin/teams/{team['id']}", json={"captain_id": b_id, "member_ids": [b_id, a_id]}
    )
    assert resp.status_code == 400

    # 有报名：删除 -> 400。
    resp = admin_client.delete(f"/api/admin/teams/{team['id']}")
    assert resp.status_code == 400
    assert "无法删除" in resp.json()["detail"]


def test_admin_delete_team_without_registrations(admin_client, client):
    a_id = _register(client, "team_k", "team_k@example.com")
    team = _create_team(admin_client, _team_payload(a_id, [a_id]))

    resp = admin_client.delete(f"/api/admin/teams/{team['id']}")
    assert resp.status_code == 200
    assert admin_client.get("/api/admin/teams").json() == []

    resp = admin_client.delete(f"/api/admin/teams/{team['id']}")
    assert resp.status_code == 404


def test_admin_team_requires_admin(client):
    _register(client, "plain_user", "plain@example.com")
    resp = client.get("/api/admin/teams")
    assert resp.status_code == 403
