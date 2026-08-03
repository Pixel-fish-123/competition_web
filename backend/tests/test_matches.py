"""TDD tests for the match lifecycle / gameplay-session API (todo 14).

Flow: create competition (round_robin, group_size=6) -> 6 individual
registrations -> approve (direct DB write; no approval endpoint yet) ->
transition ongoing (engine schedule materializes Match rows) -> referee starts
a match (GameSession via plugin) -> referee records result (engine advances).

Metis E1 (single-elim draw -> 400), E3 (referee must be in referee_ids -> 403),
C7 (no manual match creation), V-checks (finished guard on uncompleted
matches) are all covered.
"""

from app.db import SessionLocal
from app.models.competition import Competition
from app.models.match import Match
from app.models.registration import Registration
from app.services import match_service

PASSWORD = "secret123"

# triangle_occupy's generate_tasks_from_songs requires >= 23 songs, each with
# a name, a valid type (Glitch/Chaos/Hard) and a difficulty level.
SONG_LIB = {
    "songs": [
        {"name": f"歌曲{i:02d}", "type": "Glitch", "level": f"{i % 10 + 6}"}
        for i in range(1, 24)
    ]
}

BASE_PAYLOAD = {
    "name": "对局测试比赛",
    "description": "生命周期测试",
    "participant_type": "individual",
    "tournament_format": "round_robin",
    "format_config": {"group_size": 6},
    "points_rule": {"1": 10, "2": 5},
    "gameplay_plugin": "triangle_occupy",
    "song_lib": SONG_LIB,
    "referee_ids": [],
    "max_participants": 6,
}


def _register(client, username, email):
    # Clear the jar first: auth/register sets a fresh "token" cookie; any
    # manually-set cookie from a previous user would otherwise conflict.
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
    """Register a user, flip role to "referee" via DB, restore admin cookie."""
    from app.models.user import User

    referee_id, referee_token = _register(client, username, email)
    _as_user(client, admin_token)
    with SessionLocal() as db:
        user = db.get(User, referee_id)
        user.role = "referee"
        db.commit()
    return referee_id, referee_token


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


def _seed_players_and_approve(client, admin_token, competition_id, count):
    """Register ``count`` individual players, register them, approve via DB."""
    player_ids = []
    for i in range(count):
        pid, ptoken = _register(client, f"player_{i}", f"player{i}@example.com")
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


def _get_matches(client, competition_id):
    resp = client.get(f"/api/competitions/{competition_id}/matches")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ------------------------------------------------------------ happy lifecycle


def test_round_robin_schedule_generated_on_ongoing(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, _ = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 6)

    resp = _transition(admin_client, comp_id, "ongoing")
    assert resp.status_code == 200, resp.text

    # 6 participants, one group of 6 -> 5 rounds x 3 matches = 15.
    matches = _get_matches(admin_client, comp_id)
    assert len(matches) == 15
    rounds = {m["round_id"] for m in matches}
    assert rounds == {1, 2, 3, 4, 5}
    # Every round has exactly 3 real matches.
    for round_id in (1, 2, 3, 4, 5):
        round_matches = [m for m in matches if m["round_id"] == round_id]
        assert len(round_matches) == 3
        assert all(m["participant_b"] is not None for m in round_matches)
    # No match is pre-finished (no byes with 6 participants).
    assert all(m["status"] == "pending" for m in matches)
    assert all(m["result_type"] is None for m in matches)


def test_full_lifecycle_start_result_finish(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    matches = _get_matches(admin_client, comp_id)
    first = matches[0]
    assert first["status"] == "pending"

    # Referee starts the match -> GameSession created.
    _as_user(admin_client, referee_token)
    resp = admin_client.post(f"/api/matches/{first['id']}/start", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["session_id"] is not None
    assert resp.json()["status"] == "in_progress"

    # Detail shows the session state.
    detail = admin_client.get(f"/api/matches/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["session"]["plugin_name"] == "triangle_occupy"
    assert detail.json()["session"]["state"] is not None
    assert detail.json()["match"]["status"] == "in_progress"
    assert detail.json()["match"]["referee_id"] == referee_id

    # Record result -> match finished, result_type win.
    resp = admin_client.post(
        f"/api/matches/{first['id']}/result",
        json={"winner": first["participant_a"], "score_a": 90.0, "score_b": 70.0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "finished"
    assert data["result_type"] == "win"
    assert data["result"]["winner"] == first["participant_a"]
    assert data["result"]["score_a"] == 90.0


def test_play_all_matches_then_finish_competition(admin_client):
    """Engine advances through every match; finished guard passes at the end."""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    matches = _get_matches(admin_client, comp_id)
    for match in matches:
        _as_user(admin_client, referee_token)
        start = admin_client.post(f"/api/matches/{match['id']}/start", json={})
        assert start.status_code == 200, start.text
        result = admin_client.post(
            f"/api/matches/{match['id']}/result",
            json={"winner": match["participant_a"]},
        )
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "finished"
        assert result.json()["result_type"] == "win"

    # All 15 matches finished -> competition can be finished.
    _as_user(admin_client, admin_token)
    resp = _transition(admin_client, comp_id, "finished")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "finished"


def test_finish_with_uncompleted_matches_returns_400(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, _ = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    resp = _transition(admin_client, comp_id, "finished")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "存在未完成的对局"


# ------------------------------------------------------------------ permissions


def test_start_match_as_non_assigned_referee_returns_403(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, _ = _make_referee(admin_client, admin_token, username="referee_a")
    _, other_referee_token = _make_referee(
        admin_client, admin_token, username="referee_b", email="referee_b@example.com"
    )
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    match_id = _get_matches(admin_client, comp_id)[0]["id"]
    _as_user(admin_client, other_referee_token)
    resp = admin_client.post(f"/api/matches/{match_id}/start", json={})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "非本场比赛裁判"


def test_start_match_as_player_returns_403(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, _ = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    player_ids = _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    match_id = _get_matches(admin_client, comp_id)[0]["id"]
    # Re-login as a player (register helper above stored player tokens implicitly;
    # restore a player cookie by registering again -> auto-login).
    _, player_token = _register(admin_client, "lurker", "lurker@example.com")
    assert player_ids
    _as_user(admin_client, player_token)
    resp = admin_client.post(f"/api/matches/{match_id}/start", json={})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "权限不足"


def test_result_for_pending_match_returns_400(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    match = _get_matches(admin_client, comp_id)[0]
    _as_user(admin_client, referee_token)
    resp = admin_client.post(
        f"/api/matches/{match['id']}/result", json={"winner": match["participant_a"]}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "对局未进行中"


def test_list_matches_unauthenticated_returns_401(client):
    with SessionLocal() as db:
        comp = Competition(name="未认证比赛", status="ongoing", created_by=1)
        db.add(comp)
        db.commit()
        comp_id = comp.id
    resp = client.get(f"/api/competitions/{comp_id}/matches")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或登录已失效"


def test_get_match_detail_unknown_returns_404(admin_client):
    resp = admin_client.get("/api/matches/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "对局不存在"


# ------------------------------------------------------------- single elim / byes


def _seed_single_elim(admin_client, count=5):
    """Create single-elim competition with ``count`` approved players -> ongoing."""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(
        admin_client,
        tournament_format="single_elim",
        format_config={},
        max_participants=count,
        referee_ids=[referee_id],
    )
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, count)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200
    return comp_id, referee_token


def test_single_elim_bye_auto_finishes_on_start(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(
        admin_client,
        tournament_format="single_elim",
        format_config={},
        max_participants=5,
        referee_ids=[referee_id],
    )
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 5)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    matches = _get_matches(admin_client, comp_id)
    # A bye is a round-1 slot with participant_b None (later rounds have BOTH
    # participants unknown -> None/None, which is not a bye).
    bye_matches = [
        m
        for m in matches
        if m["participant_b"] is None and m["participant_a"] is not None
    ]
    real_matches = [m for m in matches if m["participant_b"] is not None]
    # 5 players -> bracket of 8: 4 round-1 pairings, 3 of them byes.
    assert len(bye_matches) == 3
    assert len(real_matches) == 1

    _as_user(admin_client, referee_token)
    bye = bye_matches[0]
    resp = admin_client.post(f"/api/matches/{bye['id']}/start", json={})
    assert resp.status_code == 200, resp.text
    # Bye auto-finishes: no session, match already finished as a win.
    assert resp.json()["session_id"] is None
    assert resp.json()["status"] == "finished"
    detail = admin_client.get(f"/api/matches/{bye['id']}").json()
    assert detail["match"]["status"] == "finished"
    assert detail["match"]["result_type"] == "win"
    assert detail["match"]["result"]["winner"] == bye["participant_a"]
    assert detail["session"] is None


def test_single_elim_draw_returns_400(admin_client):
    comp_id, referee_token = _seed_single_elim(admin_client, count=5)
    matches = _get_matches(admin_client, comp_id)
    real = next(m for m in matches if m["participant_b"] is not None)

    _as_user(admin_client, referee_token)
    resp = admin_client.post(f"/api/matches/{real['id']}/start", json={})
    assert resp.status_code == 200, resp.text
    resp = admin_client.post(
        f"/api/matches/{real['id']}/result", json={"is_draw": True}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "单败淘汰不允许平局，裁判须指定胜者"


def test_single_elim_winner_record_advances_engine(admin_client):
    """Recording the round-1 winner lets the next round's match be started."""
    comp_id, referee_token = _seed_single_elim(admin_client, count=5)
    matches = _get_matches(admin_client, comp_id)
    real = next(m for m in matches if m["participant_b"] is not None)

    _as_user(admin_client, referee_token)
    start = admin_client.post(f"/api/matches/{real['id']}/start", json={})
    assert start.status_code == 200, start.text
    resp = admin_client.post(
        f"/api/matches/{real['id']}/result", json={"winner": real["participant_a"]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "finished"

    # Round 2 match has unknown participants in DB but must be startable now.
    round2 = next(
        m
        for m in matches
        if m["round_id"] == 2 and m["participant_a"] is None and m["participant_b"] is None
    )
    resp = admin_client.post(f"/api/matches/{round2['id']}/start", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["session_id"] is not None


def test_single_elim_later_round_start_write_back_participants(admin_client):
    """todo 3: start_match 把引擎解析的参赛者回写到 Match 行（前端依赖）。

    单败淘汰后续轮次排表时 participant_a/b 为 None；开赛后必须落库，
    否则前端 match 接口永远读到 null、无法推导 participant_id。
    详情接口还需带 gameplay_plugin（前端按插件名解析玩法组件）。
    """
    comp_id, referee_token = _seed_single_elim(admin_client, count=5)
    matches = _get_matches(admin_client, comp_id)
    real = next(m for m in matches if m["participant_b"] is not None)
    round2 = next(
        m
        for m in matches
        if m["round_id"] == 2 and m["participant_a"] is None and m["participant_b"] is None
    )

    # 前序首轮真实对局完赛（3 个轮空自动晋级）。
    _as_user(admin_client, referee_token)
    resp = admin_client.post(f"/api/matches/{real['id']}/start", json={})
    assert resp.status_code == 200, resp.text
    resp = admin_client.post(
        f"/api/matches/{real['id']}/result", json={"winner": real["participant_a"]}
    )
    assert resp.status_code == 200, resp.text

    # 开赛前：后续轮次 participant_a/b 仍为 None，但详情已带 gameplay_plugin。
    detail = admin_client.get(f"/api/matches/{round2['id']}").json()
    assert detail["match"]["participant_a"] is None
    assert detail["match"]["participant_b"] is None
    assert detail["match"]["gameplay_plugin"] == "triangle_occupy"

    # 开赛：引擎解析出真实参赛者并回写落库。
    resp = admin_client.post(f"/api/matches/{round2['id']}/start", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["session_id"] is not None

    # 用确定性重建引擎验证回写值与引擎解析结果一致（防 stale_state）。
    with SessionLocal() as db:
        match_row = db.get(Match, round2["id"])
        assert match_row is not None
        comp = db.get(Competition, comp_id)
        engine = match_service._rebuild_engine(db, comp)
        match_service._replay_finished(db, comp, engine)
        exp_a, exp_b = engine._resolve_participants(match_row.engine_match_id)
        assert match_row.participant_a is not None
        assert match_row.participant_b is not None
        assert match_row.participant_a == exp_a
        assert match_row.participant_b == exp_b

    # API 详情同源读取：participant 非空 + gameplay_plugin。
    detail = admin_client.get(f"/api/matches/{round2['id']}").json()
    assert detail["match"]["participant_a"] is not None
    assert detail["match"]["participant_b"] is not None
    assert detail["match"]["gameplay_plugin"] == "triangle_occupy"
