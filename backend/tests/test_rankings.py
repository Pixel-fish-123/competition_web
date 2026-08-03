"""TDD tests for 排行榜 API (todo 17): 场次排名 + 全局榜.

GET /api/rankings/competition/{id} rebuilds the tournament engine (same
deterministic rebuild + replay as match_service) and returns the current
standings; GET /api/rankings/global delegates to the points leaderboard.
"""

from app.db import SessionLocal
from app.models.competition import Competition
from app.models.registration import Registration
from app.models.user import User

PASSWORD = "secret123"

SONG_LIB = {
    "songs": [
        {"name": f"歌曲{i:02d}", "type": "Glitch", "level": f"{i % 10 + 6}"}
        for i in range(1, 24)
    ]
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


def _make_referee(client, admin_token, username="referee_r", email="referee_r@example.com"):
    referee_id, referee_token = _register(client, username, email)
    _as_user(client, admin_token)
    with SessionLocal() as db:
        user = db.get(User, referee_id)
        user.role = "referee"
        db.commit()
    return referee_id, referee_token


def _create_ok(admin_client, **overrides):
    payload = {
        "name": "排行榜测试比赛",
        "description": "场次排名",
        "participant_type": "individual",
        "tournament_format": "round_robin",
        "format_config": {"group_size": 6},
        "points_rule": {"1": 100, "2": 60, "3": 40, "default": 10},
        "gameplay_plugin": "triangle_occupy",
        "song_lib": SONG_LIB,
        "referee_ids": [],
        "max_participants": 6,
        **overrides,
    }
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
        pid, ptoken = _register(client, f"rk_player_{i}", f"rk{i}@example.com")
        player_ids.append(pid)
        _as_user(client, ptoken)
        resp = client.post(
            f"/api/competitions/{competition_id}/register",
            json={"participant_type": "individual"},
        )
        assert resp.status_code == 200, resp.text
    _as_user(client, admin_token)
    with SessionLocal() as db:
        for reg in db.query(Registration).filter(
            Registration.competition_id == competition_id
        ):
            reg.status = "approved"
        db.commit()
    return player_ids


def _play_all_matches(client, referee_token, competition_id):
    resp = client.get(f"/api/competitions/{competition_id}/matches")
    assert resp.status_code == 200, resp.text
    for match in resp.json():
        _as_user(client, referee_token)
        start = client.post(f"/api/matches/{match['id']}/start", json={})
        assert start.status_code == 200, start.text
        result = client.post(
            f"/api/matches/{match['id']}/result",
            json={"winner": match["participant_a"]},
        )
        assert result.status_code == 200, result.text


def _run_competition(client, admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    player_ids = _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200
    _play_all_matches(client, referee_token, comp_id)
    _as_user(client, admin_token)  # restore admin cookie for follow-up transitions
    return comp_id, player_ids


def test_competition_rankings_rows_after_matches_recorded(admin_client):
    comp_id, player_ids = _run_competition(admin_client, admin_client)
    resp = admin_client.get(f"/api/rankings/competition/{comp_id}")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 6
    assert [row["rank"] for row in rows] == [1, 2, 3, 4, 5, 6]
    assert {row["participant_id"] for row in rows} == set(player_ids)
    # wins strictly descending (6-player round-robin, no draws).
    wins = [row["wins"] for row in rows]
    assert wins == sorted(wins, reverse=True)
    assert wins[0] == 5.0
    assert all(row["participant_name"] is not None for row in rows)


def test_competition_rankings_unknown_competition_404(admin_client):
    resp = admin_client.get("/api/rankings/competition/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "比赛不存在"


def test_global_rankings_delegate_to_leaderboard(admin_client):
    comp_id, _ = _run_competition(admin_client, admin_client)
    # Finish the competition so settlement creates the transactions.
    assert _transition(admin_client, comp_id, "finished").status_code == 200

    resp = admin_client.get("/api/rankings/global")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 6
    assert [row["total"] for row in rows] == [100.0, 60.0, 40.0, 10.0, 10.0, 10.0]
    assert set(rows[0]) == {"user_id", "username", "total", "competition_sum", "activity_sum"}


def test_rankings_global_matches_points_leaderboard(admin_client):
    comp_id, _ = _run_competition(admin_client, admin_client)
    assert _transition(admin_client, comp_id, "finished").status_code == 200
    g = admin_client.get("/api/rankings/global").json()
    lb = admin_client.get("/api/points/leaderboard").json()
    assert g == lb


def test_competition_rankings_unauthenticated_401(client):
    with SessionLocal() as db:
        comp = Competition(name="未认证排行", status="ongoing", created_by=1)
        db.add(comp)
        db.commit()
        comp_id = comp.id
    resp = client.get(f"/api/rankings/competition/{comp_id}")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或登录已失效"
