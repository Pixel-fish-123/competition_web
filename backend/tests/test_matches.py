"""TDD tests for the match lifecycle API (todo 14).

Flow: create competition (swiss) -> 6 individual registrations -> approve
(direct DB write) -> transition ongoing (engine schedule materializes round-1
Match rows) -> referee starts a match -> referee records result (engine
advances, next round materializes) -> all matches played -> finished guard
passes.

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

BASE_PAYLOAD = {
    "name": "对局测试比赛",
    "description": "生命周期测试",
    "participant_type": "individual",
    "tournament_format": "swiss",
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


def test_swiss_schedule_generated_on_ongoing(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, _ = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 6)

    resp = _transition(admin_client, comp_id, "ongoing")
    assert resp.status_code == 200, resp.text

    # 6 participants, swiss -> 只物化第 1 轮：3 场真实对局，全部 pending。
    matches = _get_matches(admin_client, comp_id)
    assert len(matches) == 3
    rounds = {m["round_id"] for m in matches}
    assert rounds == {1}
    assert all(m["participant_b"] is not None for m in matches)
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

    # Referee starts the match -> in_progress (no gameplay session created).
    _as_user(admin_client, referee_token)
    resp = admin_client.post(f"/api/matches/{first['id']}/start", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "in_progress"

    # Detail shows the match is live (no GameSession — 玩法已解耦，模型已删).
    detail = admin_client.get(f"/api/matches/{first['id']}")
    assert detail.status_code == 200
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
    """Engine advances through every match; finished guard passes at the end.

    瑞士轮逐轮物化：循环打到无未完成对局为止。
    """
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    _as_user(admin_client, referee_token)
    while True:
        matches = _get_matches(admin_client, comp_id)
        pending = [m for m in matches if m["status"] != "finished"]
        if not pending:
            break
        for match in pending:
            start = admin_client.post(f"/api/matches/{match['id']}/start", json={})
            assert start.status_code == 200, start.text
            result = admin_client.post(
                f"/api/matches/{match['id']}/result",
                json={"winner": match["participant_a"]},
            )
            assert result.status_code == 200, result.text
            assert result.json()["status"] == "finished"
            assert result.json()["result_type"] == "win"

    # All matches finished -> competition can be finished.
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
    assert resp.json()["detail"] == "对局未进行中或已结束"


def test_finished_match_can_rerecord_result(admin_client):
    """比赛结束后裁判仍可人工修改结果（用户需求：导入日志后可调整）。"""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 4)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    match = _get_matches(admin_client, comp_id)[0]
    _as_user(admin_client, referee_token)
    # 首次记分
    assert (
        admin_client.post(
            f"/api/matches/{match['id']}/start", json={}
        ).status_code
        == 200
    )
    resp = admin_client.post(
        f"/api/matches/{match['id']}/result",
        json={
            "winner": match["participant_a"],
            "is_draw": False,
            "score_a": 10,
            "score_b": 5,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "finished"

    # 重新记分（修改结果）
    resp2 = admin_client.post(
        f"/api/matches/{match['id']}/result",
        json={
            "winner": match["participant_b"],
            "is_draw": False,
            "score_a": 3,
            "score_b": 7,
        },
    )
    assert resp2.status_code == 200
    assert resp2.json()["result"]["winner"] == match["participant_b"]
    assert resp2.json()["result"]["score_a"] == 3
    assert resp2.json()["result"]["score_b"] == 7


# ------------------------------------------------- randomize sides (issue 2)


def _pending_two_player_match(admin_client):
    """2 名选手 swiss -> 1 场真实 pending 对局。返回 (match_id, referee_token)。"""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 2)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200
    match = _get_matches(admin_client, comp_id)[0]
    assert match["status"] == "pending"
    assert match["participant_b"] is not None
    return match["id"], match["participant_a"], match["participant_b"], referee_token


def test_randomize_sides_keeps_pair_and_swaps_sometimes(admin_client):
    match_id, orig_a, orig_b, referee_token = _pending_two_player_match(admin_client)
    _as_user(admin_client, referee_token)

    swapped_any = False
    for _ in range(8):
        resp = admin_client.post(f"/api/matches/{match_id}/randomize-sides", json={})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # 双方 id 不变，只是顺序可能交换。
        assert {data["participant_a"], data["participant_b"]} == {orig_a, orig_b}
        assert data["participant_a"] != data["participant_b"]
        if (data["participant_a"], data["participant_b"]) != (orig_a, orig_b):
            swapped_any = True
            break
    assert swapped_any, "8 次随机选边应至少出现一次顺序交换（1/2^8 概率极小）"


def test_randomize_sides_rejected_when_started(admin_client):
    match_id, _, _, referee_token = _pending_two_player_match(admin_client)
    _as_user(admin_client, referee_token)
    assert admin_client.post(f"/api/matches/{match_id}/start", json={}).status_code == 200

    resp = admin_client.post(f"/api/matches/{match_id}/randomize-sides", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "仅未开始的比赛可以进行随机选边"


def test_randomize_sides_requires_assigned_referee(admin_client):
    admin_token = admin_client.cookies.get("token")
    referee_id, _ = _make_referee(admin_client, admin_token, username="referee_a")
    _, other_referee_token = _make_referee(
        admin_client, admin_token, username="referee_b", email="referee_b@example.com"
    )
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 2)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200
    match_id = _get_matches(admin_client, comp_id)[0]["id"]

    _as_user(admin_client, other_referee_token)
    resp = admin_client.post(f"/api/matches/{match_id}/randomize-sides", json={})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "非本场比赛裁判"


def test_randomize_sides_on_bye_match_returns_400(admin_client):
    """单败轮空对局（participant_b=None）不可随机选边。"""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(
        admin_client,
        tournament_format="single_elim",
        format_config={},
        max_participants=3,
        referee_ids=[referee_id],
    )
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 3)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    matches = _get_matches(admin_client, comp_id)
    bye = next(m for m in matches if m["participant_b"] is None)
    _as_user(admin_client, referee_token)
    resp = admin_client.post(f"/api/matches/{bye['id']}/randomize-sides", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "对局双方尚未确定，无法随机选边"


def test_result_lock_prevents_rerecord(admin_client):
    """issue 14：保存结果（lock=true）后结果锁定，任何再次 /result 均 400。"""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 4)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    match = _get_matches(admin_client, comp_id)[0]
    _as_user(admin_client, referee_token)
    assert (
        admin_client.post(f"/api/matches/{match['id']}/start", json={}).status_code
        == 200
    )
    # 首次记分 + 锁定。
    resp = admin_client.post(
        f"/api/matches/{match['id']}/result",
        json={
            "winner": match["participant_a"],
            "is_draw": False,
            "score_a": 10,
            "score_b": 5,
            "lock": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["result_locked"] is True

    # 锁定后任何修改都被拒绝。
    resp2 = admin_client.post(
        f"/api/matches/{match['id']}/result",
        json={"winner": match["participant_b"], "is_draw": False, "score_a": 3, "score_b": 7},
    )
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "结果已锁定，无法更改"

    # 结果保持首次提交的值。
    detail = admin_client.get(f"/api/matches/{match['id']}").json()
    assert detail["match"]["result_locked"] is True
    assert detail["match"]["result"]["winner"] == match["participant_a"]


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
    # Bye auto-finishes: no gameplay session, match already finished as a win.
    assert resp.json()["status"] == "finished"
    detail = admin_client.get(f"/api/matches/{bye['id']}").json()
    assert detail["match"]["status"] == "finished"
    assert detail["match"]["result_type"] == "win"
    assert detail["match"]["result"]["winner"] == bye["participant_a"]


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
    assert resp.json()["status"] == "in_progress"


def test_single_elim_later_round_start_write_back_participants(admin_client):
    """todo 3: start_match 把引擎解析的参赛者回写到 Match 行（前端依赖）。

    单败淘汰后续轮次排表时 participant_a/b 为 None；开赛后必须落库，
    否则前端 match 接口永远读到 null、无法推导 participant_id。
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

    # 开赛前：后续轮次 participant_a/b 仍为 None。
    detail = admin_client.get(f"/api/matches/{round2['id']}").json()
    assert detail["match"]["participant_a"] is None
    assert detail["match"]["participant_b"] is None

    # 开赛：引擎解析出真实参赛者并回写落库（不再创建玩法会话）。
    resp = admin_client.post(f"/api/matches/{round2['id']}/start", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "in_progress"

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

    # API 详情同源读取：participant 非空。
    detail = admin_client.get(f"/api/matches/{round2['id']}").json()
    assert detail["match"]["participant_a"] is not None
    assert detail["match"]["participant_b"] is not None
