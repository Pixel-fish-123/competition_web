"""TDD tests for 双轨积分流水、比赛结算（手动调用）与排行榜后端 (todo 17, 9).

Flows: individual round-robin competition (points_rule) -> finish all matches
-> transition finished (NO auto-settle; todo 9 用户确认 ①A) -> tests that need
competition rewards call ``points_service.settle_competition_points`` directly
-> verify PointTransaction rows / balance / leaderboard. Team competition:
each member receives the FULL rank amount (Metis C6/E15, reason notes
队伍<队名>). Admin manual grants (kind=manual) and the permission gates
(player 403, anonymous 401) round the suite out.
"""

from app.db import SessionLocal
from app.models.competition import Competition
from app.models.point import PointTransaction
from app.models.registration import Registration
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services import points_service

PASSWORD = "secret123"

SONG_LIB = {
    "songs": [
        {"name": f"歌曲{i:02d}", "type": "Glitch", "level": f"{i % 10 + 6}"}
        for i in range(1, 24)
    ]
}

BASE_PAYLOAD = {
    "name": "积分测试比赛",
    "description": "积分结算",
    "participant_type": "individual",
    "tournament_format": "round_robin",
    "format_config": {"group_size": 6},
    "points_rule": {"1": 100, "2": 60, "3": 40, "default": 10},
    "gameplay_plugin": "triangle_occupy",
    "song_lib": SONG_LIB,
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
    """Referee starts + records a win for participant_a in every match."""
    for match in _get_matches(client, competition_id):
        _as_user(client, referee_token)
        start = client.post(f"/api/matches/{match['id']}/start", json={})
        assert start.status_code == 200, start.text
        result = client.post(
            f"/api/matches/{match['id']}/result",
            json={"winner": match["participant_a"]},
        )
        assert result.status_code == 200, result.text


def _run_individual_competition(client, admin_client, **overrides):
    """Full flow through to finished (no auto-settle since todo 9). Returns
    player ids/tokens. Callers that need competition rewards must invoke
    ``_settle_via_service`` explicitly."""
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


def _transactions_for_competition(competition_id):
    with SessionLocal() as db:
        return (
            db.query(PointTransaction)
            .filter(
                PointTransaction.ref_competition_id == competition_id,
                PointTransaction.kind == "competition",
            )
            .all()
        )


def _settle_via_service(competition_id):
    """Directly invoke the retained settlement service.

    finished 流转已移除自动结算（todo 9），结算逻辑只保留在服务层供手动/
    测试调用 —— 需要 competition 流水的测试显式调用本 helper。
    """
    with SessionLocal() as db:
        comp = db.get(Competition, competition_id)
        return points_service.settle_competition_points(db, comp)


# ------------------------------------------------------- settlement on finish


def test_finish_competition_produces_no_auto_transactions(admin_client):
    comp_id, player_ids, _ = _run_individual_competition(admin_client, admin_client)
    # finished 流转已移除自动结算：不得产生任何 competition 流水。
    assert _transactions_for_competition(comp_id) == []

    # Admin 手动发放仍然可用，产生一笔 manual 流水。
    resp = admin_client.post(
        "/api/admin/points",
        json={
            "user_id": player_ids[0],
            "amount": 100.0,
            "kind": "manual",
            "reason": "手动奖励",
        },
    )
    assert resp.status_code == 200, resp.text
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


def test_individual_rewards_follow_points_rule_and_reason(admin_client):
    comp_id, player_ids, _ = _run_individual_competition(admin_client, admin_client)
    _settle_via_service(comp_id)
    with SessionLocal() as db:
        comp = db.get(Competition, comp_id)
        standings = points_service.get_competition_standings(db, comp)
    # Standings are best-first; rank = 1-based position (all 6 participants).
    ranked = [(rank, row.participant_id) for rank, row in enumerate(standings, start=1)]
    assert len(ranked) == 6
    assert [pid for _, pid in ranked] == sorted(player_ids)

    txs = _transactions_for_competition(comp_id)
    by_user = {tx.user_id: tx for tx in txs}
    # Rank 1/2/3 get rule values; ranks 4-6 get the default 10.
    expected = {rank: points for rank, points in [(1, 100), (2, 60), (3, 40)]}
    for rank, participant_id in ranked:
        user_id = participant_id
        tx = by_user[user_id]
        want = expected.get(rank, 10)
        assert tx.amount == want, f"rank {rank} user {user_id}: got {tx.amount}"
        assert tx.reason == f"比赛名次·第{rank}名"


def test_points_rule_missing_rank_grants_default_when_present(admin_client):
    # Rule without ranks 2/3 -> default 10 applies to everyone except rank 1.
    comp_id, _, _ = _run_individual_competition(
        admin_client, admin_client, points_rule={"1": 100, "default": 10}
    )
    _settle_via_service(comp_id)
    txs = _transactions_for_competition(comp_id)
    assert len(txs) == 6
    assert sorted(tx.amount for tx in txs) == [10, 10, 10, 10, 10, 100]


def test_points_rule_no_default_grants_zero_to_unranked(admin_client):
    # Only rank 1 rewarded; no "default" key -> ranks 2-6 get nothing.
    comp_id, _, _ = _run_individual_competition(
        admin_client, admin_client, points_rule={"1": 100}
    )
    _settle_via_service(comp_id)
    txs = _transactions_for_competition(comp_id)
    assert len(txs) == 1
    assert txs[0].amount == 100
    assert txs[0].reason == "比赛名次·第1名"


def test_settle_is_idempotent(admin_client):
    comp_id, _, _ = _run_individual_competition(admin_client, admin_client)
    # finished 不再自动结算：首次手动调用产生 6 条流水，再次调用返回 []。
    assert len(_settle_via_service(comp_id)) == 6
    assert len(_transactions_for_competition(comp_id)) == 6

    with SessionLocal() as db:
        comp = db.get(Competition, comp_id)
        again = points_service.settle_competition_points(db, comp)
        assert again == []
    assert len(_transactions_for_competition(comp_id)) == 6


def test_settle_unfinished_competition_raises(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, _ = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    with SessionLocal() as db:
        comp = db.get(Competition, comp_id)
        try:
            points_service.settle_competition_points(db, comp)
        except ValueError as e:
            assert "未完成" in str(e)
        else:
            raise AssertionError("expected ValueError for unfinished competition")
    assert _transactions_for_competition(comp_id) == []


# ------------------------------------------------- team reward (Metis C6/E15)


def _create_team_with_members(client, team_name, captain, members):
    """Register users, create a team, add members. Returns (team_id, ids)."""
    captain_id, captain_token = captain
    member_ids = []
    for member in members:
        mid, _mtoken = member
        member_ids.append(mid)
    _as_user(client, captain_token)
    resp = client.post("/api/teams", json={"name": team_name})
    assert resp.status_code == 200, resp.text
    team_id = resp.json()["id"]
    for mid in member_ids:
        resp = client.post(f"/api/teams/{team_id}/members", json={"user_id": mid})
        assert resp.status_code == 200, resp.text
    return team_id, [captain_id, *member_ids]


def _run_team_competition(client, admin_client):
    """Two teams round-robin; team A (3 members) beats team B (captain only)."""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)

    t1 = _register(client, "team_a_cap", "team_a@example.com")
    t1_members = [_register(client, "team_a_b", "team_a_b@example.com"),
                  _register(client, "team_a_c", "team_a_c@example.com")]
    t2 = _register(client, "team_b_cap", "team_b@example.com")
    team_a_id, team_a_ids = _create_team_with_members(
        client, "Alpha", t1, t1_members
    )
    team_b_id, team_b_ids = _create_team_with_members(client, "Beta", t2, [])
    _as_user(client, admin_token)
    comp_id = _create_ok(
        admin_client,
        name="队伍积分赛",
        participant_type="team",
        format_config={"group_size": 4},
        max_participants=4,
        referee_ids=[referee_id],
    )
    assert _transition(admin_client, comp_id, "registration").status_code == 200

    # Captains register their teams.
    _as_user(client, t1[1])
    assert client.post(
        f"/api/competitions/{comp_id}/register",
        json={"participant_type": "team", "team_id": team_a_id},
    ).status_code == 200
    _as_user(client, t2[1])
    assert client.post(
        f"/api/competitions/{comp_id}/register",
        json={"participant_type": "team", "team_id": team_b_id},
    ).status_code == 200
    _as_user(client, admin_token)
    with SessionLocal() as db:
        for reg in db.query(Registration).filter(
            Registration.competition_id == comp_id
        ):
            reg.status = "approved"
        db.commit()

    assert _transition(admin_client, comp_id, "ongoing").status_code == 200
    # 2 teams -> exactly 1 match; team A (lower team id, participant_a) wins.
    _play_all_matches(client, referee_token, comp_id)
    _as_user(client, admin_token)
    assert _transition(admin_client, comp_id, "finished").status_code == 200
    return comp_id, team_a_id, team_a_ids, team_b_id, team_b_ids


def test_team_reward_full_amount_to_each_member(admin_client):
    comp_id, team_a_id, team_a_ids, team_b_id, team_b_ids = _run_team_competition(
        admin_client, admin_client
    )
    _settle_via_service(comp_id)
    txs = _transactions_for_competition(comp_id)
    # 3 team-A members x full 100 + team-B captain x 60 = 4 transactions.
    assert len(txs) == 4
    by_user = {tx.user_id: tx for tx in txs}
    with SessionLocal() as db:
        team_a = db.get(Team, team_a_id)
        team_b = db.get(Team, team_b_id)
    assert team_a is not None
    assert team_b is not None

    for user_id in team_a_ids:
        tx = by_user[user_id]
        assert tx.amount == 100, f"team-A member {user_id} must get FULL 100"
        assert tx.reason == f"比赛名次·第1名·队伍{team_a.name}"
    for user_id in team_b_ids:
        tx = by_user[user_id]
        assert tx.amount == 60
        assert tx.reason == f"比赛名次·第2名·队伍{team_b.name}"


# ---------------------------------------------------------- points API


def _player_points_me(client, token):
    _as_user(client, token)
    return client.get("/api/points/me")


def test_points_me_returns_balance_and_transactions(admin_client):
    comp_id, _, player_tokens = _run_individual_competition(admin_client, admin_client)
    _settle_via_service(comp_id)
    resp = _player_points_me(admin_client, player_tokens[0])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Lowest user id -> participant_a in every match -> rank 1 -> 100 points.
    assert data["balance"] == 100.0
    assert len(data["transactions"]) == 1
    tx = data["transactions"][0]
    assert tx["kind"] == "competition"
    assert tx["amount"] == 100.0
    assert tx["reason"] == "比赛名次·第1名"


def test_points_me_unauthenticated_returns_401(client):
    resp = client.get("/api/points/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或登录已失效"


def test_leaderboard_ordered_by_total_desc(admin_client):
    comp_id, _, _ = _run_individual_competition(admin_client, admin_client)
    _settle_via_service(comp_id)
    resp = admin_client.get("/api/points/leaderboard")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 6
    totals = [row["total"] for row in rows]
    assert totals == [100.0, 60.0, 40.0, 10.0, 10.0, 10.0]
    assert totals == sorted(totals, reverse=True)
    for row in rows:
        assert set(row) == {"user_id", "username", "total", "competition_sum", "activity_sum"}
        assert row["competition_sum"] == row["total"]
        assert row["activity_sum"] == 0.0


def test_admin_grant_activity_points_increases_balance(admin_client):
    comp_id, player_ids, player_tokens = _run_individual_competition(
        admin_client, admin_client
    )
    _settle_via_service(comp_id)
    rank1 = player_ids[0]
    resp = admin_client.post(
        "/api/admin/points",
        json={"user_id": rank1, "amount": 50.0, "kind": "activity", "reason": "活动奖励"},
    )
    assert resp.status_code == 200, resp.text

    me = _player_points_me(admin_client, player_tokens[0])
    assert me.status_code == 200, me.text
    data = me.json()
    assert data["balance"] == 150.0
    kinds = [tx["kind"] for tx in data["transactions"]]
    assert kinds == ["activity", "competition"]  # newest first
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
        assert audit.detail["user_id"] == rank1
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
