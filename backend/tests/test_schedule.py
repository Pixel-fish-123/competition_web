"""QQ 字段（个人资料/管理端）与赛程只读接口 + 赛程图页面的测试。"""

from datetime import datetime

from app.db import SessionLocal
from app.models.competition import Competition
from app.models.match import Match
from app.models.registration import Registration
from app.models.team import Team, TeamMember
from app.models.user import User

PASSWORD = "secret123"

BASE_PAYLOAD = {
    "name": "赛程接口测试比赛",
    "description": "赛程接口测试",
    "participant_type": "mixed",
    "tournament_format": "swiss",
    "referee_ids": [],
    "max_participants": 6,
}


def _register(client, username, email, qq=None):
    client.cookies.clear()
    payload = {"username": username, "email": email, "password": PASSWORD}
    if qq:
        payload["qq"] = qq
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"], client.cookies.get("token")


def _as_user(client, token):
    client.cookies.clear()
    client.cookies.set("token", token)


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
    player_ids = []
    for i in range(count):
        pid, ptoken = _register(
            client,
            f"player_{i}",
            f"player{i}@example.com",
            qq=f"10000{i}",
        )
        player_ids.append(pid)
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
    return player_ids


# ------------------------------------------------------------ QQ 字段


def test_register_with_qq_and_update_me(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "qq_user",
            "email": "qq_user@example.com",
            "password": PASSWORD,
            "qq": "123456789",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["qq"] == "123456789"

    # 修改 QQ
    resp = client.patch("/api/auth/me", json={"qq": "987654321"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["qq"] == "987654321"

    # 空串清除 QQ
    resp = client.patch("/api/auth/me", json={"qq": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["qq"] == ""

    # 非数字拒绝
    resp = client.patch("/api/auth/me", json={"qq": "abc"})
    assert resp.status_code == 422


def test_admin_create_and_patch_qq(admin_client):
    resp = admin_client.post(
        "/api/admin/users",
        json={
            "username": "admin_created",
            "email": "admin_created@example.com",
            "password": PASSWORD,
            "role": "player",
            "qq": "555666",
        },
    )
    assert resp.status_code == 200, resp.text
    user_id = resp.json()["id"]
    assert resp.json()["qq"] == "555666"

    resp = admin_client.patch(f"/api/admin/users/{user_id}", json={"qq": "777888"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["qq"] == "777888"


# ------------------------------------------------------------ 赛程接口


def test_schedule_current_404_without_ongoing(client):
    resp = client.get("/api/schedule/current")
    assert resp.status_code == 404


def test_schedule_endpoints_return_names_and_qqs(admin_client, client):
    admin_token = admin_client.cookies.get("token")
    comp_id = _create_ok(admin_client)
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    # 指定比赛 + 当前进行中比赛，两个接口应一致
    for url in (
        f"/api/competitions/{comp_id}/schedule",
        "/api/schedule/current",
    ):
        resp = client.get(url)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["competition"]["id"] == comp_id
        assert data["competition"]["status"] == "ongoing"
        assert len(data["matches"]) > 0
        m = data["matches"][0]
        assert m["round_id"] == 1
        assert m["participant_a"]["type"] == "individual"
        assert m["participant_a"]["qqs"] == ["100000"]
        assert m["participant_a"]["name"] == "player_0"
        assert m["participant_b"]["qqs"] == ["100001"]


def test_schedule_team_participant_returns_member_qqs(client):
    """团队报名：队伍名 + 全体成员 QQ（直插 DB 数据，不走完整报名流程）。"""
    with SessionLocal() as db:
        admin = User(
            username="team_admin",
            email="team_admin@example.com",
            password_hash="x",
            role="admin",
            status="active",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        captain = User(
            username="captain",
            email="captain@example.com",
            password_hash="x",
            qq="111111",
            role="player",
            status="active",
        )
        member = User(
            username="member",
            email="member@example.com",
            password_hash="x",
            qq="222222",
            role="player",
            status="active",
        )
        other = User(
            username="other",
            email="other@example.com",
            password_hash="x",
            qq="333333",
            role="player",
            status="active",
        )
        db.add_all([captain, member, other])
        db.commit()

        team = Team(name="测试队", captain_id=captain.id)
        db.add(team)
        db.commit()
        db.refresh(team)
        db.add_all(
            [
                TeamMember(team_id=team.id, user_id=captain.id),
                TeamMember(team_id=team.id, user_id=member.id),
            ]
        )
        comp = Competition(
            name="团队赛比赛",
            participant_type="mixed",
            tournament_format="swiss",
            status="ongoing",
            created_by=admin.id,
        )
        db.add(comp)
        db.commit()
        db.refresh(comp)
        db.add_all(
            [
                Registration(
                    competition_id=comp.id,
                    participant_type="team",
                    team_id=team.id,
                    user_id=captain.id,
                    status="approved",
                ),
                Registration(
                    competition_id=comp.id,
                    participant_type="individual",
                    user_id=other.id,
                    status="approved",
                ),
            ]
        )
        db.add(
            Match(
                competition_id=comp.id,
                round_id=1,
                engine_match_id=1,
                participant_a=team.id,
                participant_b=other.id,
                status="pending",
            )
        )
        db.commit()

    resp = client.get("/api/schedule/current")
    assert resp.status_code == 200, resp.text
    m = resp.json()["matches"][0]
    assert m["participant_a"]["type"] == "team"
    assert m["participant_a"]["name"] == "测试队"
    assert sorted(m["participant_a"]["qqs"]) == ["111111", "222222"]
    assert m["participant_b"]["type"] == "individual"
    assert m["participant_b"]["qqs"] == ["333333"]


# ------------------------------------------------------------ 赛程图页面


def test_bracket_page_renders_html(client):
    with SessionLocal() as db:
        admin = User(
            username="bracket_admin",
            email="bracket_admin@example.com",
            password_hash="x",
            role="admin",
            status="active",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        alice = User(
            username="alice",
            email="alice@example.com",
            password_hash="x",
            qq="100001",
            role="player",
            status="active",
        )
        bob = User(
            username="bob",
            email="bob@example.com",
            password_hash="x",
            qq="100002",
            role="player",
            status="active",
        )
        db.add_all([alice, bob])
        db.commit()
        comp = Competition(
            name="签表测试",
            participant_type="individual",
            tournament_format="single_elim",
            status="ongoing",
            created_by=admin.id,
        )
        db.add(comp)
        db.commit()
        db.refresh(comp)
        comp_id = comp.id
        db.add_all(
            [
                Registration(
                    competition_id=comp.id,
                    participant_type="individual",
                    user_id=alice.id,
                    status="approved",
                ),
                Registration(
                    competition_id=comp.id,
                    participant_type="individual",
                    user_id=bob.id,
                    status="approved",
                ),
            ]
        )
        db.add(
            Match(
                competition_id=comp.id,
                round_id=1,
                engine_match_id=1,
                participant_a=alice.id,
                participant_b=bob.id,
                status="pending",
                result={"winner": None, "is_draw": False, "score_a": None, "score_b": None},
            )
        )
        db.commit()

    resp = client.get(f"/competitions/{comp_id}/bracket")
    assert resp.status_code == 200, resp.text
    assert "签表测试" in resp.text
    assert "alice" in resp.text
    assert "bob" in resp.text
    assert "待开始" in resp.text


def test_bracket_four_player_single_elim_round_titles(admin_client, client):
    """4 人单败淘汰：末轮单场 + 次末轮单场 → 末轮应为季军赛，决赛标题不偏移。"""
    admin_token = admin_client.cookies.get("token")
    comp_id = _create_ok(admin_client, tournament_format="single_elim")
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(client, admin_token, comp_id, 4)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    resp = client.get(f"/competitions/{comp_id}/bracket")
    assert resp.status_code == 200, resp.text
    text = resp.text
    assert "决赛" in text
    assert "季军赛" in text
    # 4 人签表没有半决赛轮；旧实现会把决赛误标成半决赛。
    assert "半决赛" not in text


def test_schedule_ambiguous_id_prefers_team(client):
    """参赛者 id 同时命中队伍与个人报名时，按报名行类型解析（优先队伍）。"""
    with SessionLocal() as db:
        user_a = User(
            username="collision_user",
            email="collision_user@example.com",
            password_hash="x",
            qq="400001",
            role="player",
            status="active",
        )
        admin = User(
            username="collision_admin",
            email="collision_admin@example.com",
            password_hash="x",
            role="admin",
            status="active",
        )
        captain = User(
            username="collision_captain",
            email="collision_captain@example.com",
            password_hash="x",
            qq="400002",
            role="player",
            status="active",
        )
        db.add_all([user_a, admin, captain])
        db.commit()
        db.refresh(user_a)

        # 造队伍直到队伍 id 恰好等于 user_a.id（两表各自自增，必然撞上）。
        team = None
        n = 0
        while team is None or team.id != user_a.id:
            n += 1
            candidate = Team(name=f"撞号队{n}", captain_id=captain.id)
            db.add(candidate)
            db.commit()
            db.refresh(candidate)
            if candidate.id == user_a.id:
                team = candidate

        reg_time = datetime(2026, 1, 1)
        member_time = datetime(2025, 12, 31)
        comp = Competition(
            name="撞号比赛",
            participant_type="mixed",
            tournament_format="swiss",
            status="ongoing",
            created_by=admin.id,
        )
        db.add(comp)
        db.commit()
        db.refresh(comp)
        # 个人报名先插入（旧实现的 .first() 会错误命中它）。
        db.add(
            Registration(
                competition_id=comp.id,
                participant_type="individual",
                user_id=user_a.id,
                status="approved",
                created_at=reg_time,
            )
        )
        db.add(
            Registration(
                competition_id=comp.id,
                participant_type="team",
                team_id=team.id,
                user_id=captain.id,
                status="approved",
                created_at=reg_time,
            )
        )
        db.add(TeamMember(team_id=team.id, user_id=captain.id, created_at=member_time))
        db.add(
            Match(
                competition_id=comp.id,
                round_id=1,
                engine_match_id=1,
                participant_a=user_a.id,
                participant_b=None,
                status="pending",
            )
        )
        db.commit()
        collided_id = user_a.id
        team_name = team.name

    resp = client.get("/api/schedule/current")
    assert resp.status_code == 200, resp.text
    m = resp.json()["matches"][0]
    assert m["participant_a"]["type"] == "team"
    assert m["participant_a"]["name"] == team_name
    assert m["participant_a"]["qqs"] == ["400002"]
    assert collided_id == team.id


def test_schedule_team_member_joined_after_registration_excluded(client):
    """报名时刻后才入队的成员不应出现在名单 QQ 里。"""
    with SessionLocal() as db:
        admin = User(
            username="cutoff_admin",
            email="cutoff_admin@example.com",
            password_hash="x",
            role="admin",
            status="active",
        )
        captain = User(
            username="cutoff_captain",
            email="cutoff_captain@example.com",
            password_hash="x",
            qq="500001",
            role="player",
            status="active",
        )
        late = User(
            username="cutoff_late",
            email="cutoff_late@example.com",
            password_hash="x",
            qq="500002",
            role="player",
            status="active",
        )
        db.add_all([admin, captain, late])
        db.commit()
        team = Team(name="截点队", captain_id=captain.id)
        db.add(team)
        db.commit()
        db.refresh(team)
        comp = Competition(
            name="截点比赛",
            participant_type="mixed",
            tournament_format="swiss",
            status="ongoing",
            created_by=admin.id,
        )
        db.add(comp)
        db.commit()
        db.refresh(comp)
        reg_time = datetime(2026, 1, 1)
        db.add(
            Registration(
                competition_id=comp.id,
                participant_type="team",
                team_id=team.id,
                user_id=captain.id,
                status="approved",
                created_at=reg_time,
            )
        )
        db.add(TeamMember(team_id=team.id, user_id=captain.id, created_at=datetime(2025, 12, 31)))
        # 报名之后才入队 → 不应被拉进名单。
        db.add(TeamMember(team_id=team.id, user_id=late.id, created_at=datetime(2026, 1, 2)))
        db.add(
            Match(
                competition_id=comp.id,
                round_id=1,
                engine_match_id=1,
                participant_a=team.id,
                participant_b=None,
                status="pending",
            )
        )
        db.commit()

    resp = client.get("/api/schedule/current")
    assert resp.status_code == 200, resp.text
    m = resp.json()["matches"][0]
    assert m["participant_a"]["type"] == "team"
    assert m["participant_a"]["qqs"] == ["500001"]
