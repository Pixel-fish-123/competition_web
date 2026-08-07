"""todo 7: admin create / hard-delete user CRUD tests.

POST /api/admin/users: admin 创建账号（角色/密码直接指定）；重复用户名 400；
role 非法 400；player 403。
DELETE /api/admin/users/{id}: 硬删除 + 手工级联清理（Registration /
PointTransaction / TeamMember / 队长队伍删除；AuditLog.user_id 与
Match.referee_id 置 NULL 防悬空）；保护规则（删自己 / 最后一个 admin /
比赛创建者 / 未完结对局参赛者 → 400）。

基线特征（修前失败）：admin 无创建/删除账号端点 —— 本文件即新增功能的回归。
"""

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.competition import Competition
from app.models.match import Match
from app.models.point import PointTransaction
from app.models.registration import Registration
from app.models.team import Team, TeamMember
from app.models.user import User

PASSWORD = "secret123"


def _create_user(admin_client, username="referee_x", email="rx@example.com", role="referee"):
    resp = admin_client.post(
        "/api/admin/users",
        json={"username": username, "email": email, "password": PASSWORD, "role": role},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _admin_id(admin_client):
    return admin_client.get("/api/auth/me").json()["id"]


# ------------------------------------------------------------------- create


def test_admin_creates_user_and_can_login(admin_client):
    resp = admin_client.post(
        "/api/admin/users",
        json={"username": "new_referee", "email": "nr@example.com", "password": "pass1234", "role": "referee"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["username"] == "new_referee"
    assert data["role"] == "referee"
    assert data["status"] == "active"
    # 响应不泄漏密码哈希
    assert "password_hash" not in data

    # 创建出的账号能直接用该密码登录（角色以 DB 为准）
    c = TestClient(app)
    login = c.post("/api/auth/login", json={"username": "new_referee", "password": "pass1234"})
    assert login.status_code == 200, login.text
    assert login.json()["role"] == "referee"


def test_admin_creates_player_and_admin_roles(admin_client):
    player_id = _create_user(admin_client, username="new_player", email="np@example.com", role="player")
    admin_id = _create_user(admin_client, username="new_admin", email="na@example.com", role="admin")
    with SessionLocal() as db:
        assert db.get(User, player_id).role == "player"
        assert db.get(User, admin_id).role == "admin"


def test_create_duplicate_username_400(admin_client):
    _create_user(admin_client, username="dup_user")
    resp = admin_client.post(
        "/api/admin/users",
        json={"username": "dup_user", "email": "other@example.com", "password": PASSWORD, "role": "player"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "用户名已存在"


def test_create_duplicate_email_400(admin_client):
    _create_user(admin_client, username="first_user", email="same@example.com")
    resp = admin_client.post(
        "/api/admin/users",
        json={"username": "second_user", "email": "same@example.com", "password": PASSWORD, "role": "player"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "邮箱已被注册"


def test_create_invalid_role_400(admin_client):
    resp = admin_client.post(
        "/api/admin/users",
        json={"username": "bad_role", "email": "bad@example.com", "password": PASSWORD, "role": "superadmin"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "无效的角色"


def test_create_invalid_email_422(admin_client):
    resp = admin_client.post(
        "/api/admin/users",
        json={"username": "bad_email", "email": "not-an-email", "password": PASSWORD, "role": "player"},
    )
    assert resp.status_code == 422


def test_create_short_password_422(admin_client):
    resp = admin_client.post(
        "/api/admin/users",
        json={"username": "short_pw", "email": "sp@example.com", "password": "123", "role": "player"},
    )
    assert resp.status_code == 422


def test_player_cannot_create_user(client):
    resp = client.post(
        "/api/auth/register",
        json={"username": "player_a", "email": "pa@example.com", "password": PASSWORD},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/admin/users",
        json={"username": "evil", "email": "evil@example.com", "password": PASSWORD, "role": "admin"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "权限不足"


# ------------------------------------------------------------------- delete


def test_player_cannot_delete_user(client):
    resp = client.post(
        "/api/auth/register",
        json={"username": "player_a", "email": "pa@example.com", "password": PASSWORD},
    )
    uid = resp.json()["id"]
    resp = client.delete(f"/api/admin/users/{uid}")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "权限不足"


def test_delete_nonexistent_user_404(admin_client):
    resp = admin_client.delete("/api/admin/users/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "用户不存在"


def test_delete_self_400(admin_client):
    me = admin_client.get("/api/auth/me").json()
    resp = admin_client.delete(f"/api/admin/users/{me['id']}")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "不能删除自己"
    # 自己还在
    with SessionLocal() as db:
        assert db.get(User, me["id"]) is not None


def test_delete_last_admin_400(admin_client):
    """系统不能没有管理员：删掉唯一剩余 admin（即自己）被拒。"""
    me = admin_client.get("/api/auth/me").json()
    assert me["role"] == "admin"
    with SessionLocal() as db:
        assert db.query(User).filter(User.role == "admin").count() == 1
    resp = admin_client.delete(f"/api/admin/users/{me['id']}")
    assert resp.status_code == 400
    with SessionLocal() as db:
        assert db.query(User).filter(User.role == "admin").count() == 1


def test_delete_non_last_admin_other_admin_succeeds(admin_client):
    """存在多个 admin 时，删除另一 admin 放行（不是最后一个）。"""
    admin_b = _create_user(admin_client, username="admin_b", email="ab@example.com", role="admin")
    resp = admin_client.delete(f"/api/admin/users/{admin_b}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}
    with SessionLocal() as db:
        assert db.get(User, admin_b) is None
        assert db.query(User).filter(User.role == "admin").count() == 1


def test_delete_competition_creator_400(admin_client):
    """Competition.created_by FK NOT NULL：创建过比赛的用户禁止删除。"""
    uid = _create_user(admin_client, username="creator", email="c@example.com", role="referee")
    with SessionLocal() as db:
        db.add(Competition(name="该用户创建的比赛", status="draft", created_by=uid))
        db.commit()

    resp = admin_client.delete(f"/api/admin/users/{uid}")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "该用户创建了比赛，无法删除"
    with SessionLocal() as db:
        assert db.get(User, uid) is not None


def test_delete_user_with_unfinished_match_opponent_wins(admin_client):
    """issue 3：删除未完结对局的参赛者不再被阻塞 —— 对局按轮空计算，
    直接判对手获胜（0:0, result_type=win）。"""
    admin_id = _admin_id(admin_client)
    uid = _create_user(admin_client, username="player_x", email="px@example.com", role="player")
    with SessionLocal() as db:
        comp = Competition(name="进行中比赛", status="ongoing", created_by=admin_id, referee_ids=[])
        db.add(comp)
        db.flush()
        db.add(
            Match(
                competition_id=comp.id,
                round_id=1,
                participant_a=admin_id,
                participant_b=uid,
                engine_match_id=1,
                status="pending",
            )
        )
        db.commit()
        comp_id = comp.id
        match_id = db.query(Match).filter(Match.competition_id == comp.id).one().id

    resp = admin_client.delete(f"/api/admin/users/{uid}")
    assert resp.status_code == 200, resp.text

    with SessionLocal() as db:
        assert db.get(User, uid) is None
        match = db.get(Match, match_id)
        assert match is not None
        assert match.status == "finished"
        assert match.result_type == "win"
        assert match.result["winner"] == admin_id
        assert match.result["score_a"] == 0.0
        assert match.result["score_b"] == 0.0
        assert comp_id is not None


def test_delete_user_cascade_cleanup(admin_client):
    """硬删除 + 完整级联：报名/积分/队伍成员/队长队伍清理；
    AuditLog.user_id 与 Match.referee_id 置 NULL（保留审计与对局）。"""
    admin_id = _admin_id(admin_client)
    uid = _create_user(admin_client, username="victim", email="v@example.com", role="referee")

    with SessionLocal() as db:
        comp = Competition(name="级联测试比赛", status="ongoing", created_by=admin_id, referee_ids=[])
        db.add(comp)
        db.flush()
        comp_id = comp.id
        team = Team(name="受害者队", captain_id=uid)
        db.add(team)
        db.flush()
        team_id = team.id
        db.add(TeamMember(team_id=team_id, user_id=uid))
        db.add(TeamMember(team_id=team_id, user_id=admin_id))
        db.add(
            Registration(
                competition_id=comp_id,
                participant_type="individual",
                user_id=uid,
                status="approved",
            )
        )
        db.add(PointTransaction(user_id=uid, amount=10.0, kind="manual", reason="test"))
        match = Match(
            competition_id=comp_id,
            round_id=1,
            participant_a=admin_id,
            participant_b=uid,
            engine_match_id=1,
            status="finished",  # finished: 不触发未完结对局保护
            referee_id=uid,
            result={"winner": admin_id, "is_draw": False, "score_a": 1.0, "score_b": 0.0},
        )
        db.add(match)
        db.flush()
        match_id = match.id
        db.add(AuditLog(user_id=uid, action="login", detail={"username": "victim"}))
        db.add(
            AuditLog(
                user_id=admin_id,
                action="points_grant",
                detail={"username": "victim"},
            )
        )
        db.commit()

    resp = admin_client.delete(f"/api/admin/users/{uid}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    with SessionLocal() as db:
        # 用户行已删
        assert db.get(User, uid) is None
        # 报名 / 积分 / 队伍成员（含该用户与队伍）全清
        assert db.query(Registration).filter(Registration.user_id == uid).count() == 0
        assert db.query(PointTransaction).filter(PointTransaction.user_id == uid).count() == 0
        assert db.query(TeamMember).filter(TeamMember.user_id == uid).count() == 0
        assert db.query(Team).filter(Team.captain_id == uid).count() == 0
        assert db.query(TeamMember).filter(TeamMember.team_id == team_id).count() == 0
        # 对局保留，referee_id 置 NULL（防悬空）；participant_b 是普通 int 列
        # （无 FK），按计划保留
        match_row = db.get(Match, match_id)
        assert match_row is not None
        assert match_row.referee_id is None
        assert match_row.participant_b == uid
        # 审计追溯：被删用户的旧审计置 NULL，admin 的审计保留
        login_logs = db.query(AuditLog).filter(AuditLog.action == "login").all()
        assert len(login_logs) == 1
        assert login_logs[0].user_id is None
        grant_logs = db.query(AuditLog).filter(AuditLog.action == "points_grant").all()
        assert len(grant_logs) == 1
        assert grant_logs[0].user_id == admin_id
        # 删除动作本身有审计
        assert db.query(AuditLog).filter(AuditLog.action == "admin_delete_user").count() == 1


def test_delete_user_removes_membership_only_keeps_team(admin_client):
    """非队长成员的队伍保留（只删成员行，不误删他人队伍）。"""
    admin_id = _admin_id(admin_client)
    member = _create_user(admin_client, username="member_x", email="mx@example.com", role="player")
    with SessionLocal() as db:
        team = Team(name="他人队伍", captain_id=admin_id)
        db.add(team)
        db.flush()
        team_id = team.id
        db.add(TeamMember(team_id=team_id, user_id=member))
        db.commit()

    resp = admin_client.delete(f"/api/admin/users/{member}")
    assert resp.status_code == 200, resp.text
    with SessionLocal() as db:
        assert db.get(User, member) is None
        assert db.get(Team, team_id) is not None  # 队伍还在
        assert db.query(TeamMember).filter(TeamMember.user_id == member).count() == 0
