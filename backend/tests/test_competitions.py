"""TDD tests for the competition management API (todo 8).

Admin is bootstrapped via the ``admin_client`` fixture (register + role flip
through a direct DB write — the app has no admin bootstrap yet). Referee users
are created the same way: register a normal player then flip role to
"referee" via ``SessionLocal``. Because register auto-logs-in and overwrites
the "token" cookie, the admin token is saved/restored around those helper
calls (same cookie-jar discipline as tests/test_registrations.py).
"""

from datetime import datetime

from app.db import SessionLocal
from app.models.competition import Competition
from app.models.match import GameSession, Match
from app.models.point import PointTransaction
from app.models.registration import Registration
from app.models.user import User

PASSWORD = "secret123"

# Minimal valid create payload; tests override specific fields.
BASE_PAYLOAD = {
    "name": "测试比赛",
    "description": "描述",
    "banner_url": "https://example.com/banner.png",
    "participant_type": "mixed",
    "tournament_format": "round_robin",
    "format_config": {"groups": 2},
    "points_rule": {"1": 10, "2": 5},
    "gameplay_plugin": "triangle_occupy",
    "song_lib": {"songs": ["song_a"]},
    "referee_ids": [],
    "max_participants": 50,
}


def _register(client, username, email):
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _make_referee(client, admin_token, username="referee_a", email="referee@example.com"):
    """Register a user, flip role to "referee" via DB, restore admin cookie."""
    referee_id = _register(client, username, email)
    client.cookies.set("token", admin_token)
    with SessionLocal() as db:
        user = db.get(User, referee_id)
        user.role = "referee"
        db.commit()
    return referee_id


def _seed_competition(name="种子比赛", status="draft"):
    """Seed a Competition directly via DB (for public/no-admin scenarios)."""
    with SessionLocal() as db:
        comp = Competition(name=name, status=status, created_by=1)
        db.add(comp)
        db.commit()
        db.refresh(comp)
        return comp.id


def _create(admin_client, **overrides):
    payload = {**BASE_PAYLOAD, **overrides}
    return admin_client.post("/api/competitions", json=payload)


def _create_ok(admin_client, **overrides):
    resp = _create(admin_client, **overrides)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _transition(admin_client, competition_id, status):
    return admin_client.post(
        f"/api/competitions/{competition_id}/status", json={"status": status}
    )


# ---------------------------------------------------------------- public API


def test_public_list_without_auth(client):
    comp_id = _seed_competition("公开比赛")
    resp = client.get("/api/competitions")
    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == [comp_id]


def test_public_list_ordered_by_id_desc(client):
    first = _seed_competition("比赛A")
    second = _seed_competition("比赛B")
    resp = client.get("/api/competitions")
    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == [second, first]


def test_public_detail_without_auth(client):
    comp_id = _seed_competition("公开详情")
    resp = client.get(f"/api/competitions/{comp_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "公开详情"


def test_get_nonexistent_competition_returns_404(client):
    resp = client.get("/api/competitions/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "比赛不存在"


# ----------------------------------------------------------- create (admin)


def test_player_cannot_create_competition(client):
    _register(client, "player_a", "pa@example.com")
    resp = client.post("/api/competitions", json={"name": "比赛"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "权限不足"


def test_admin_create_competition_full_config_round_trip(admin_client):
    admin_token = admin_client.cookies.get("token")
    admin_id = admin_client.get("/api/auth/me").json()["id"]
    referee_id = _make_referee(admin_client, admin_token)

    resp = _create(
        admin_client,
        name="全配置比赛",
        description="全配置描述",
        participant_type="team",
        tournament_format="swiss",
        format_config={"rounds": 5},
        points_rule={"1": 10, "2": 5},
        gameplay_plugin="triangle_occupy",
        song_lib={"songs": ["song_a"]},
        referee_ids=[referee_id],
        max_participants=32,
        start_time="2026-08-10T09:00:00Z",
        end_time="2026-08-10T18:00:00Z",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "全配置比赛"
    assert data["description"] == "全配置描述"
    assert data["banner_url"] == "https://example.com/banner.png"
    assert data["participant_type"] == "team"
    assert data["tournament_format"] == "swiss"
    assert data["format_config"] == {"rounds": 5}
    assert data["points_rule"] == {"1": 10, "2": 5}
    assert data["gameplay_plugin"] == "triangle_occupy"
    assert data["song_lib"] == {"songs": ["song_a"]}
    assert data["referee_ids"] == [referee_id]
    assert data["max_participants"] == 32
    assert data["status"] == "draft"
    assert data["created_by"] == admin_id
    assert datetime.fromisoformat(data["start_time"]).year == 2026
    assert datetime.fromisoformat(data["end_time"]).year == 2026


def test_create_defaults_draft_and_empty_config(admin_client):
    # Minimal payload: schema/model defaults must fill the rest.
    resp = admin_client.post("/api/competitions", json={"name": "默认比赛"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "draft"
    assert data["tournament_format"] == "round_robin"
    assert data["gameplay_plugin"] == "triangle_occupy"
    assert data["format_config"] == {}
    assert data["points_rule"] == {}
    assert data["referee_ids"] == []
    assert data["participant_type"] == "mixed"
    assert data["max_participants"] == 50


def test_create_with_player_role_referee_returns_400(admin_client):
    admin_token = admin_client.cookies.get("token")
    player_id = _register(admin_client, "player_a", "pa@example.com")
    admin_client.cookies.set("token", admin_token)

    resp = _create(admin_client, referee_ids=[player_id])
    assert resp.status_code == 400
    assert resp.json()["detail"] == "裁判组成员必须是 referee 角色"


def test_create_with_nonexistent_referee_returns_404(admin_client):
    resp = _create(admin_client, referee_ids=[9999])
    assert resp.status_code == 404
    assert resp.json()["detail"] == "裁判用户不存在"


def test_create_invalid_tournament_format_returns_422(admin_client):
    resp = _create(admin_client, tournament_format="double_elim")
    assert resp.status_code == 422


# ------------------------------------------------------------------ update


def test_admin_update_name_and_description(admin_client):
    comp_id = _create_ok(admin_client)
    resp = admin_client.patch(
        f"/api/competitions/{comp_id}",
        json={"name": "改名比赛", "description": "新描述"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "改名比赛"
    assert data["description"] == "新描述"
    # Unrelated fields untouched.
    assert data["tournament_format"] == "round_robin"
    assert data["status"] == "draft"


def test_admin_update_assigns_referees(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client)

    resp = admin_client.patch(
        f"/api/competitions/{comp_id}", json={"referee_ids": [referee_id]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["referee_ids"] == [referee_id]


def test_admin_update_referee_player_role_returns_400(admin_client):
    admin_token = admin_client.cookies.get("token")
    player_id = _register(admin_client, "player_a", "pa@example.com")
    admin_client.cookies.set("token", admin_token)
    comp_id = _create_ok(admin_client)

    resp = admin_client.patch(
        f"/api/competitions/{comp_id}", json={"referee_ids": [player_id]}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "裁判组成员必须是 referee 角色"


def test_patch_nonexistent_competition_returns_404(admin_client):
    resp = admin_client.patch("/api/competitions/9999", json={"name": "xx"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "比赛不存在"


# ------------------------------------------------------------ status machine


def test_status_full_chain_draft_to_finished(admin_client):
    comp_id = _create_ok(admin_client)
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    resp = _transition(admin_client, comp_id, "ongoing")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ongoing"
    resp = _transition(admin_client, comp_id, "finished")
    assert resp.status_code == 200
    assert resp.json()["status"] == "finished"


def test_illegal_transition_ongoing_to_draft_returns_400(admin_client):
    comp_id = _create_ok(admin_client)
    _transition(admin_client, comp_id, "registration")
    _transition(admin_client, comp_id, "ongoing")
    resp = _transition(admin_client, comp_id, "draft")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "非法状态流转"


def test_finished_is_terminal(admin_client):
    comp_id = _create_ok(admin_client)
    for status in ("registration", "ongoing", "finished"):
        assert _transition(admin_client, comp_id, status).status_code == 200
    for status in ("draft", "registration", "ongoing", "cancelled"):
        resp = _transition(admin_client, comp_id, status)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "非法状态流转"


def test_draft_to_cancelled_then_cancelled_is_terminal(admin_client):
    comp_id = _create_ok(admin_client)
    resp = _transition(admin_client, comp_id, "cancelled")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    resp = _transition(admin_client, comp_id, "ongoing")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "非法状态流转"


def test_invalid_status_value_returns_422(admin_client):
    comp_id = _create_ok(admin_client)
    resp = admin_client.post(
        f"/api/competitions/{comp_id}/status", json={"status": "running"}
    )
    assert resp.status_code == 422


def test_status_transition_nonexistent_competition_returns_404(admin_client):
    resp = admin_client.post(
        "/api/competitions/9999/status", json={"status": "registration"}
    )
    assert resp.status_code == 404


# ------------------------------------------------------------------- delete


def test_delete_draft_competition(admin_client):
    comp_id = _create_ok(admin_client)
    resp = admin_client.delete(f"/api/competitions/{comp_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}
    assert admin_client.get("/api/competitions").json() == []


def test_delete_finished_competition_returns_200_and_cascades(admin_client):
    comp_id = _create_ok(admin_client)
    for status in ("registration", "ongoing", "finished"):
        assert _transition(admin_client, comp_id, status).status_code == 200

    # Seed business data that must be cascade-cleaned: a Match, its
    # GameSession, a PointTransaction and a Registration.
    with SessionLocal() as db:
        match = Match(
            competition_id=comp_id,
            round_id=1,
            engine_match_id=1,
            status="finished",
        )
        db.add(match)
        db.flush()
        db.add(
            GameSession(
                match_id=match.id,
                plugin_name="triangle_occupy",
                config={},
            )
        )
        db.add(
            PointTransaction(
                user_id=1,
                amount=10,
                kind="competition",
                ref_competition_id=comp_id,
                reason="比赛名次·第1名",
            )
        )
        db.add(
            Registration(
                competition_id=comp_id,
                user_id=1,
                participant_type="individual",
                status="approved",
            )
        )
        db.commit()

    resp = admin_client.delete(f"/api/competitions/{comp_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    # Cascade cleanup verified: no orphaned business rows remain.
    with SessionLocal() as db:
        assert db.get(Competition, comp_id) is None
        assert (
            db.query(Match).filter(Match.competition_id == comp_id).count() == 0
        )
        assert (
            db.query(GameSession)
            .join(Match, GameSession.match_id == Match.id)
            .filter(Match.competition_id == comp_id)
            .count()
            == 0
        )
        assert (
            db.query(PointTransaction)
            .filter(PointTransaction.ref_competition_id == comp_id)
            .count()
            == 0
        )
        assert (
            db.query(Registration)
            .filter(Registration.competition_id == comp_id)
            .count()
            == 0
        )


def test_delete_ongoing_competition_returns_400(admin_client):
    comp_id = _create_ok(admin_client)
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200
    resp = admin_client.delete(f"/api/competitions/{comp_id}")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "进行中的比赛无法删除"


def test_player_cannot_delete_competition(client):
    _register(client, "player_a", "pa@example.com")
    comp_id = _seed_competition("选手删除", status="finished")
    resp = client.delete(f"/api/competitions/{comp_id}")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "权限不足"


def test_delete_draft_with_registrations_removes_them(admin_client):
    admin_token = admin_client.cookies.get("token")
    comp_id = _create_ok(admin_client)
    assert _transition(admin_client, comp_id, "registration").status_code == 200

    # A player registers (auto-login swaps the cookie to the player).
    _register(admin_client, "player_a", "pa@example.com")
    resp = admin_client.post(
        f"/api/competitions/{comp_id}/register", json={"participant_type": "individual"}
    )
    assert resp.status_code == 200, resp.text
    admin_client.cookies.set("token", admin_token)  # back to admin

    # Cancelled is deletable; move the competition there first.
    assert _transition(admin_client, comp_id, "cancelled").status_code == 200
    resp = admin_client.delete(f"/api/competitions/{comp_id}")
    assert resp.status_code == 200, resp.text

    # Registrations are gone (explicit delete in the endpoint).
    with SessionLocal() as db:
        assert (
            db.query(Registration)
            .filter(Registration.competition_id == comp_id)
            .count()
            == 0
        )
        assert db.get(Competition, comp_id) is None
    # The registrations list endpoint confirms the competition no longer exists.
    resp = admin_client.get(f"/api/competitions/{comp_id}/registrations")
    assert resp.status_code == 404
