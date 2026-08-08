"""TDD tests for 积分流水与排行榜后端 (todo 17).

积分只能由管理员手动发放产生（POST /api/admin/points，kind=activity/manual；
issue 6 用户确认：比赛结束不自动结算，系统结算入口已整体删除）。
Flows: 跑完一场比赛 -> finished（验证不产生任何流水）-> admin 手动发放 ->
verify PointTransaction rows / balance / leaderboard。权限门禁
（player 403、匿名 401）round the suite out。
"""

from app.db import SessionLocal
from app.models.point import PointTransaction
from app.models.registration import Registration
from app.models.user import User

PASSWORD = "secret123"

BASE_PAYLOAD = {
    "name": "积分测试比赛",
    "description": "积分发放",
    "participant_type": "individual",
    "tournament_format": "swiss",
    "referee_ids": [],
    "max_participants": 6,
}


def _register(client, username, email):
    client.cookies.clear()
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"], client.cookies.get("token")


def _as_user(client, token):
    client.cookies.clear()
    client.cookies.set("token", token)


def _make_referee(client, admin_token, username="referee_a", email="referee@example.com"):
    referee_id, referee_token = _register(client, username, email)
    _as_user(client, admin_token)
    with SessionLocal() as db:
        user = db.get(User, referee_id)
        user.role = "referee"
        db.commit()
    return referee_id, referee_token


def _create_ok(admin_client, **overrides):
    payload = {**BASE_PAYLOAD, **overrides}
    resp = admin_client.post("/api/competitions", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _transition(admin_client, competition_id, status):
    return admin_client.post(
        f"/api/competitions/{competition_id}/status", json={"status": status}
    )


def _seed_players_and_approve(client, admin_token, competition_id, count):
    """Register ``count`` individual players, register + approve them via DB."""
    player_ids = []
    player_tokens = []
    for i in range(count):
        pid, ptoken = _register(client, f"player_{i}", f"player{i}@example.com")
        player_ids.append(pid)
        player_tokens.append(ptoken)
        _as_user(client, ptoken)
        resp = client.post(
            f"/api/competitions/{competition_id}/register",
            json={"participant_type": "individual"},
        )
        assert resp.status_code == 200, resp.text
    _as_user(client, admin_token)
    with SessionLocal() as db:
        regs = (
            db.query(Registration)
            .filter(Registration.competition_id == competition_id)
            .all()
        )
        assert len(regs) == count
        for reg in regs:
            reg.status = "approved"
        db.commit()
    return player_ids, player_tokens


def _get_matches(client, competition_id):
    resp = client.get(f"/api/competitions/{competition_id}/matches")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _play_all_matches(client, referee_token, competition_id):
    """Referee starts + records a win for participant_a in every match.

    循环直到无未完成对局：每轮打完调用「开始下一轮」（锁定本轮+物化下一轮）；
    单败淘汰后续轮次的参赛者在 start 时由引擎解析回写，须 start 后重新
    拉取该局详情再提交结果（不能用列表里的旧 participant_a=None）。
    """
    _as_user(client, referee_token)
    while True:
        matches = _get_matches(client, competition_id)
        pending = [m for m in matches if m["status"] != "finished"]
        if not pending:
            break
        for match in pending:
            start = client.post(f"/api/matches/{match['id']}/start", json={})
            assert start.status_code == 200, start.text
            detail = client.get(f"/api/matches/{match['id']}").json()["match"]
            result = client.post(
                f"/api/matches/{match['id']}/result",
                json={"winner": detail["participant_a"]},
            )
            assert result.status_code == 200, result.text
        # 本轮全部打完：结束本轮（锁定 + 推进下一轮）。
        for rid in {m["round_id"] for m in pending}:
            resp = client.post(
                f"/api/competitions/{competition_id}/rounds/{rid}/complete", json={}
            )
            assert resp.status_code == 200, resp.text


def _run_individual_competition(client, admin_client, **overrides):
    """Full flow through to finished (no auto-settle since issue 6). Returns
    player ids/tokens."""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id], **overrides)
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    player_ids, player_tokens = _seed_players_and_approve(
        client, admin_token, comp_id, 6
    )
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200
    _play_all_matches(client, referee_token, comp_id)
    _as_user(client, admin_token)
    resp = _transition(admin_client, comp_id, "finished")
    assert resp.status_code == 200, resp.text
    return comp_id, player_ids, player_tokens


def _grant(admin_client, user_id, amount, kind="manual", reason="手动奖励"):
    resp = admin_client.post(
        "/api/admin/points",
        json={"user_id": user_id, "amount": amount, "kind": kind, "reason": reason},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --------------------------------------------------------- finish + no settle


def test_finish_competition_produces_no_auto_transactions(admin_client):
    comp_id, player_ids, _ = _run_individual_competition(admin_client, admin_client)
    # 比赛结束不自动结算：不得产生任何 competition 流水。
    with SessionLocal() as db:
        txs = (
            db.query(PointTransaction)
            .filter(PointTransaction.ref_competition_id == comp_id)
            .all()
        )
    assert txs == []

    # Admin 手动发放仍然可用，产生一笔 manual 流水。
    _grant(admin_client, player_ids[0], 100.0)
    with SessionLocal() as db:
        txs = (
            db.query(PointTransaction)
            .filter(
                PointTransaction.user_id == player_ids[0],
                PointTransaction.kind == "manual",
            )
            .all()
        )
    assert len(txs) == 1
    assert txs[0].amount == 100.0


# ---------------------------------------------------------- points API


def _player_points_me(client, token):
    _as_user(client, token)
    return client.get("/api/points/me")


def test_points_me_returns_balance_and_transactions(admin_client):
    comp_id, player_ids, player_tokens = _run_individual_competition(
        admin_client, admin_client
    )
    _grant(admin_client, player_ids[0], 100.0, kind="activity", reason="冠军奖励")
    resp = _player_points_me(admin_client, player_tokens[0])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["balance"] == 100.0
    assert len(data["transactions"]) == 1
    tx = data["transactions"][0]
    assert tx["kind"] == "activity"
    assert tx["amount"] == 100.0
    assert tx["reason"] == "冠军奖励"


def test_points_me_unauthenticated_returns_401(client):
    resp = client.get("/api/points/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或登录已失效"


def test_leaderboard_ordered_by_total_desc(admin_client):
    comp_id, player_ids, _ = _run_individual_competition(admin_client, admin_client)
    amounts = [100.0, 60.0, 40.0, 10.0, 10.0, 10.0]
    for user_id, amount in zip(player_ids, amounts):
        _grant(admin_client, user_id, amount)
    resp = admin_client.get("/api/points/leaderboard")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 6
    totals = [row["total"] for row in rows]
    assert totals == sorted(totals, reverse=True)
    assert totals == [100.0, 60.0, 40.0, 10.0, 10.0, 10.0]
    for row in rows:
        assert set(row) == {"user_id", "username", "total", "competition_sum", "activity_sum"}
        assert row["competition_sum"] == 0.0
        assert row["activity_sum"] == 0.0


def test_admin_grant_activity_points_increases_balance(admin_client):
    comp_id, player_ids, player_tokens = _run_individual_competition(
        admin_client, admin_client
    )
    _grant(admin_client, player_ids[0], 50.0, kind="activity", reason="活动奖励")

    me = _player_points_me(admin_client, player_tokens[0])
    assert me.status_code == 200, me.text
    data = me.json()
    assert data["balance"] == 50.0
    kinds = [tx["kind"] for tx in data["transactions"]]
    assert kinds == ["activity"]
    assert data["transactions"][0]["reason"] == "活动奖励"

    # Audit trail: points_grant was written.
    from app.models.audit_log import AuditLog

    with SessionLocal() as db:
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.action == "points_grant")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.detail["user_id"] == player_ids[0]
        assert audit.detail["amount"] == 50.0


def test_player_cannot_grant_points_returns_403(client):
    _register(client, "lurker", "lurker@example.com")
    resp = client.post(
        "/api/admin/points",
        json={"user_id": 1, "amount": 10.0, "kind": "activity", "reason": "xx"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "权限不足"


def test_admin_grant_manual_kind(admin_client):
    admin_token = admin_client.cookies.get("token")
    player_id, player_token = _register(admin_client, "grantee", "grantee@example.com")
    _as_user(admin_client, admin_token)
    resp = admin_client.post(
        "/api/admin/points",
        json={"user_id": player_id, "amount": -5.0, "kind": "manual", "reason": "扣分"},
    )
    assert resp.status_code == 200, resp.text
    me = _player_points_me(admin_client, player_token)
    assert me.json()["balance"] == -5.0
