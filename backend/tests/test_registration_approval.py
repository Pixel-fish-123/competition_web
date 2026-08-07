"""TDD tests for the admin registration approval endpoints (bug 3 回归).

原缺陷：报名审批端点从未实现，报名永远停在 "pending"，导致赛程引擎只统计
status=="approved" 的参赛者，赛程永远为空、比赛无法进行。本文件覆盖：

- a) admin 审批通过（pending -> approved），重复审批 400。
- b) 审批闭环：2 名选手 approve 后置比赛 ongoing，赛程非空（核心回归）。
- c) admin 拒绝（pending -> rejected），重复拒绝 400。
- d) 非 admin 调 approve 得 403。

建赛走完整 API（POST /api/competitions + POST status），与现有
test_matches.py 的模式一致；审批走新加的 admin 端点而非直插数据库。
"""

from app.db import SessionLocal
from app.models.user import User

PASSWORD = "secret123"

BASE_PAYLOAD = {
    "name": "审批测试比赛",
    "description": "报名审批闭环",
    "participant_type": "individual",
    "tournament_format": "swiss",
    "referee_ids": [],
    "max_participants": 6,
}


def _register(client, username, email, nickname=None):
    client.cookies.clear()
    payload = {"username": username, "email": email, "password": PASSWORD}
    if nickname is not None:
        payload["nickname"] = nickname
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"], client.cookies.get("token")


def _make_referee(admin_client, admin_token, username="referee_ap", email="referee_ap@example.com"):
    """注册一名裁判（DB 翻转角色），并恢复 admin cookie。"""
    referee_id, _ = _register(admin_client, username, email)
    admin_client.cookies.set("token", admin_token)
    with SessionLocal() as db:
        user = db.get(User, referee_id)
        user.role = "referee"
        db.commit()
    return referee_id


def _create_competition(admin_client, referee_id):
    resp = admin_client.post(
        "/api/competitions",
        json={**BASE_PAYLOAD, "referee_ids": [referee_id]},
    )
    assert resp.status_code == 200, resp.text
    comp_id = resp.json()["id"]
    assert resp.json()["status"] == "draft"
    return comp_id


def _transition(admin_client, competition_id, status):
    resp = admin_client.post(
        f"/api/competitions/{competition_id}/status", json={"status": status}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _register_player(client, competition_id):
    resp = client.post(
        f"/api/competitions/{competition_id}/register",
        json={"participant_type": "individual"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"
    return resp.json()


def _approve(admin_client, competition_id, registration_id):
    return admin_client.post(
        f"/api/admin/competitions/{competition_id}/registrations/{registration_id}/approve"
    )


def _reject(admin_client, competition_id, registration_id):
    return admin_client.post(
        f"/api/admin/competitions/{competition_id}/registrations/{registration_id}/reject"
    )


def test_admin_approve_pending_registration(admin_client, client):
    admin_token = admin_client.cookies.get("token")
    referee_id = _make_referee(admin_client, admin_token)
    comp_id = _create_competition(admin_client, referee_id)
    _transition(admin_client, comp_id, "registration")

    _register(client, "ap_player", "ap@example.com")
    reg = _register_player(client, comp_id)

    resp = _approve(admin_client, comp_id, reg["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert resp.json()["participant_name"] == "ap_player"

    # 重复审批 -> 400。
    resp = _approve(admin_client, comp_id, reg["id"])
    assert resp.status_code == 400
    assert resp.json()["detail"] == "该报名已处理"


def test_approved_pair_yields_nonempty_schedule(admin_client, client):
    """核心回归（bug 3）：2 名选手 approve 后置 ongoing，赛程必须非空。"""
    admin_token = admin_client.cookies.get("token")
    referee_id = _make_referee(admin_client, admin_token)
    comp_id = _create_competition(admin_client, referee_id)
    _transition(admin_client, comp_id, "registration")

    regs = []
    for i in range(2):
        _register(client, f"ap_p{i}", f"app{i}@example.com")
        regs.append(_register_player(client, comp_id))
        assert _approve(admin_client, comp_id, regs[-1]["id"]).status_code == 200

    _transition(admin_client, comp_id, "ongoing")

    resp = admin_client.get(f"/api/competitions/{comp_id}/matches")
    assert resp.status_code == 200, resp.text
    matches = resp.json()
    assert len(matches) > 0  # 不足 2 名 approved 时赛程为空；此处已 2 名 -> 非空
    names = {m["participant_a_name"] for m in matches} | {
        m["participant_b_name"] for m in matches
    }
    assert names == {"ap_p0", "ap_p1"}  # 名字经昵称/用户名解析后回填


def test_admin_reject_pending_registration(admin_client, client):
    admin_token = admin_client.cookies.get("token")
    referee_id = _make_referee(admin_client, admin_token)
    comp_id = _create_competition(admin_client, referee_id)
    _transition(admin_client, comp_id, "registration")

    _register(client, "ap_rej", "aprej@example.com")
    reg = _register_player(client, comp_id)

    resp = _reject(admin_client, comp_id, reg["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"

    # 重复拒绝 -> 400。
    resp = _reject(admin_client, comp_id, reg["id"])
    assert resp.status_code == 400
    assert resp.json()["detail"] == "该报名已处理"


def test_non_admin_cannot_approve(admin_client, client):
    admin_token = admin_client.cookies.get("token")
    referee_id = _make_referee(admin_client, admin_token)
    comp_id = _create_competition(admin_client, referee_id)
    _transition(admin_client, comp_id, "registration")

    _register(client, "ap_plain", "applain@example.com")
    reg = _register_player(client, comp_id)

    # 普通玩家（player 角色）调 approve -> 403。
    resp = _approve(client, comp_id, reg["id"])
    assert resp.status_code == 403
    assert resp.json()["detail"] == "权限不足"


def test_approve_unknown_registration_returns_404(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id = _make_referee(admin_client, admin_token)
    comp_id = _create_competition(admin_client, referee_id)
    _transition(admin_client, comp_id, "registration")

    resp = _approve(admin_client, comp_id, 9999)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "报名记录不存在"


def test_approve_unknown_competition_returns_404(admin_client, client):
    admin_token = admin_client.cookies.get("token")
    referee_id = _make_referee(admin_client, admin_token)
    comp_id = _create_competition(admin_client, referee_id)
    _transition(admin_client, comp_id, "registration")

    _register(client, "ap_x", "apx@example.com")
    reg = _register_player(client, comp_id)

    resp = _approve(admin_client, 9999, reg["id"])
    assert resp.status_code == 404
    assert resp.json()["detail"] == "比赛不存在"
