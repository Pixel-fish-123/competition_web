"""Swiss 轮对局服务层测试 — 轮次物化 / 轮空自动完结 / 幂等 advance / finish 守卫.

Flow: create swiss competition -> registrations -> approve -> ongoing（仅 round 1
落地）-> referee 打完 round 1 -> 最后一局记分后 round 2 自动物化 -> 轮空自动
finished -> 全部轮次完结后可 finish。

覆盖三个对抗类：
- stale_state: _materialize_round 幂等 —— 重复 advance 只创建一轮对局；
- race_condition: record_match_result 在 commit 之后 fresh-check 推进轮次；
- rebuild_determinism: DB 中轮次行的 engine_match_id 与确定性重建引擎一致。
"""

from app.db import SessionLocal
from app.models.competition import Competition
from app.models.match import Match
from app.models.registration import Registration
from app.services import match_service

PASSWORD = "secret123"

# triangle_occupy's generate_tasks_from_songs requires >= 23 songs.
SONG_LIB = {
    "songs": [
        {"name": f"歌曲{i:02d}", "type": "Glitch", "level": f"{i % 10 + 6}"}
        for i in range(1, 24)
    ]
}

BASE_PAYLOAD = {
    "name": "瑞士轮测试比赛",
    "description": "轮次物化测试",
    "participant_type": "individual",
    "tournament_format": "swiss",
    "format_config": {},
    "points_rule": {"1": 10, "2": 5},
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


def _make_referee(client, admin_token, username="swiss_referee", email="swiss@example.com"):
    from app.models.user import User

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
    player_ids = []
    for i in range(count):
        pid, ptoken = _register(client, f"swiss_player_{i}", f"swiss_player{i}@example.com")
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


def _play_match(client, referee_token, match, winner):
    """Start + record result for one real match (winner wins 1-0)."""
    _as_user(client, referee_token)
    start = client.post(f"/api/matches/{match['id']}/start", json={})
    assert start.status_code == 200, start.text
    resp = client.post(
        f"/api/matches/{match['id']}/result",
        json={"winner": winner, "score_a": 1.0, "score_b": 0.0},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "finished"


def _play_round(client, referee_token, matches, winner_fn):
    """Play every real match of one round; byes are already finished."""
    for m in matches:
        if m["participant_b"] is None and m["participant_a"] is not None:
            continue  # bye — auto-finished at materialization
        _play_match(client, referee_token, m, winner_fn(m))


def _seed_swiss(admin_client, count):
    """Create a swiss competition with ``count`` approved players -> ongoing."""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id], max_participants=count)
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, count)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200
    return comp_id, referee_token


# ---------------------------------------------------------------- materialize


def test_swiss_ongoing_materializes_round_1_only(admin_client):
    """进 ongoing 时瑞士轮只落地 round 1（其余轮次待前一轮完结后逐轮生成）。"""
    comp_id, _ = _seed_swiss(admin_client, count=4)  # 3 rounds, 2 matches each

    matches = _get_matches(admin_client, comp_id)
    assert len(matches) == 2
    assert {m["round_id"] for m in matches} == {1}
    assert all(m["status"] == "pending" for m in matches)


def test_swiss_last_round1_result_materializes_round2(admin_client):
    """round 1 最后一局记分后，round 2 对局自动物化（GET /matches 可见），
    且其 engine_match_id 与确定性重建引擎一致（防 stale match_id）。"""
    comp_id, referee_token = _seed_swiss(admin_client, count=4)
    r1 = _get_matches(admin_client, comp_id)
    assert len(r1) == 2

    # Play only the first round-1 match: round 2 must NOT appear yet.
    _play_match(admin_client, referee_token, r1[0], r1[0]["participant_a"])
    after_first = _get_matches(admin_client, comp_id)
    assert {m["round_id"] for m in after_first} == {1}

    # Play the last round-1 match -> round 2 materializes.
    _play_match(admin_client, referee_token, r1[1], r1[1]["participant_a"])
    matches = _get_matches(admin_client, comp_id)
    assert {m["round_id"] for m in matches} == {1, 2}
    r2_rows = [m for m in matches if m["round_id"] == 2]
    assert len(r2_rows) == 2
    # Round 2 does not repeat round-1 opponents.
    r1_pairs = {frozenset((m["participant_a"], m["participant_b"])) for m in r1}
    r2_pairs = {frozenset((m["participant_a"], m["participant_b"])) for m in r2_rows}
    assert r1_pairs.isdisjoint(r2_pairs)

    # DB engine_match_id must match a fresh deterministic rebuild.
    with SessionLocal() as db:
        comp = db.get(Competition, comp_id)
        engine = match_service._rebuild_engine(db, comp)
        match_service._replay_finished(db, comp, engine)
        r2_engine = next(r for r in engine.generate_schedule() if r.round_number == 2)
        db_ids = [
            m.engine_match_id
            for m in db.query(Match)
            .filter(Match.competition_id == comp_id, Match.round_id == 2)
            .order_by(Match.id)
            .all()
        ]
        assert sorted(db_ids) == sorted(m.match_id for m in r2_engine.matches)


def test_swiss_round2_bye_auto_finished(admin_client):
    """奇数学员：round 2 落地时轮空对局直接 finished / win（不建会话）。"""
    comp_id, referee_token = _seed_swiss(admin_client, count=5)  # odd -> byes

    r1 = _get_matches(admin_client, comp_id)
    _play_round(admin_client, referee_token, r1, lambda m: m["participant_a"])

    r2_rows = [m for m in _get_matches(admin_client, comp_id) if m["round_id"] == 2]
    byes = [m for m in r2_rows if m["participant_b"] is None and m["participant_a"] is not None]
    assert len(byes) == 1
    bye = byes[0]
    assert bye["status"] == "finished"
    assert bye["result_type"] == "win"
    assert bye["result"]["winner"] == bye["participant_a"]


# ------------------------------------------------------------ idempotency / race


def test_swiss_double_advance_creates_rows_exactly_once(admin_client):
    """_advance_swiss_if_due 幂等：重复调用（模拟并发裁判先后触发 advance）
    不会重复创建轮次对局行。"""
    comp_id, referee_token = _seed_swiss(admin_client, count=4)
    r1 = _get_matches(admin_client, comp_id)
    _play_round(admin_client, referee_token, r1, lambda m: m["participant_a"])

    def _count_round2():
        with SessionLocal() as db:
            return (
                db.query(Match)
                .filter(Match.competition_id == comp_id, Match.round_id == 2)
                .count()
            )

    assert _count_round2() == 2
    with SessionLocal() as db:
        comp = db.get(Competition, comp_id)
        match_service._advance_swiss_if_due(db, comp)  # duplicate advance
    assert _count_round2() == 2
    with SessionLocal() as db:
        comp = db.get(Competition, comp_id)
        match_service._advance_swiss_if_due(db, comp)  # and once more
    assert _count_round2() == 2


# ------------------------------------------------------------ finish guard


def test_swiss_finish_rejects_unfinished_and_materializes_missing_round(admin_client):
    """进 finished 前若某轮因崩溃/竞态漏物化，change_status 会先补物化，
    再因存在未完成对局拒绝（400）——不会因缺轮而提前 finish。"""
    comp_id, referee_token = _seed_swiss(admin_client, count=4)
    admin_token = admin_client.cookies.get("token")  # capture BEFORE playing
    r1 = _get_matches(admin_client, comp_id)
    _play_round(admin_client, referee_token, r1, lambda m: m["participant_a"])

    # Simulate a crash that skipped round-2 materialization.
    with SessionLocal() as db:
        db.query(Match).filter(
            Match.competition_id == comp_id, Match.round_id == 2
        ).delete()
        db.commit()

    _as_user(admin_client, admin_token)
    resp = _transition(admin_client, comp_id, "finished")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "存在未完成的对局"

    # The guard's _advance_swiss_if_due re-materialized round 2 before rejecting.
    matches = _get_matches(admin_client, comp_id)
    assert {m["round_id"] for m in matches} == {1, 2}


def test_swiss_play_all_rounds_then_finish(admin_client):
    """4 人瑞士轮 = 3 轮 × 2 局。全部打完（含轮空自动完结）后可正常 finish。"""
    comp_id, referee_token = _seed_swiss(admin_client, count=4)
    admin_token = admin_client.cookies.get("token")  # capture BEFORE playing

    for round_id in (1, 2, 3):
        round_matches = [
            m for m in _get_matches(admin_client, comp_id) if m["round_id"] == round_id
        ]
        _play_round(admin_client, referee_token, round_matches, lambda m: m["participant_a"])

    _as_user(admin_client, admin_token)
    resp = _transition(admin_client, comp_id, "finished")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "finished"

    with SessionLocal() as db:
        rounds = [
            r for (r,) in db.query(Match.round_id).filter(Match.competition_id == comp_id).distinct().all()
        ]
    assert rounds == [1, 2, 3]
