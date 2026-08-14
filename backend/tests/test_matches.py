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

    每轮打完点「开始下一轮」（锁定本轮 + 物化下一轮），循环到无未完成对局。
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
        for rid in {m["round_id"] for m in pending}:
            resp = admin_client.post(
                f"/api/competitions/{comp_id}/rounds/{rid}/complete", json={}
            )
            assert resp.status_code == 200, resp.text

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


def test_bot_randomize_sides_requires_configured_token(admin_client):
    """后端未配置 BOT_API_TOKEN 时机器人随机选边接口 503。"""
    from app.config import settings

    old = settings.BOT_API_TOKEN
    settings.BOT_API_TOKEN = ""
    try:
        resp = admin_client.post(
            "/api/bot/matches/1/randomize-sides",
            headers={"X-Bot-Token": "whatever"},
        )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "后端未配置 BOT_API_TOKEN，机器人随机选边不可用"
    finally:
        settings.BOT_API_TOKEN = old


def test_bot_randomize_sides_token_auth_and_swap(admin_client):
    """机器人令牌鉴权 + 50% 交换：错误令牌 401，正确令牌保持配对并偶发交换。"""
    from app.config import settings

    old = settings.BOT_API_TOKEN
    settings.BOT_API_TOKEN = "bot-secret"
    try:
        match_id, orig_a, orig_b, _ = _pending_two_player_match(admin_client)
        url = f"/api/bot/matches/{match_id}/randomize-sides"

        resp = admin_client.post(url, headers={"X-Bot-Token": "wrong"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "机器人令牌无效"

        swapped_any = False
        for _ in range(8):
            resp = admin_client.post(url, headers={"X-Bot-Token": "bot-secret"})
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["ok"] is True
            match = data["match"]
            # 双方 id 不变，只是顺序可能交换。
            assert {match["participant_a"], match["participant_b"]} == {orig_a, orig_b}
            assert match["participant_a"] != match["participant_b"]
            if data["swapped"]:
                swapped_any = True
                break
        assert swapped_any, "8 次随机选边应至少出现一次顺序交换（1/2^8 概率极小）"
    finally:
        settings.BOT_API_TOKEN = old


def test_bot_randomize_sides_rejected_when_started(admin_client):
    """机器人随机选边与裁判版一致：已开始的比赛 400。"""
    from app.config import settings

    old = settings.BOT_API_TOKEN
    settings.BOT_API_TOKEN = "bot-secret"
    try:
        match_id, _, _, referee_token = _pending_two_player_match(admin_client)
        url = f"/api/bot/matches/{match_id}/randomize-sides"
        resp = admin_client.post(url, headers={"X-Bot-Token": "bot-secret"})
        assert resp.status_code == 200, resp.text
        # 开赛后随机选边必须失败。
        _as_user(admin_client, referee_token)
        assert admin_client.post(f"/api/matches/{match_id}/start", json={}).status_code == 200
        resp = admin_client.post(url, headers={"X-Bot-Token": "bot-secret"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "仅未开始的比赛可以进行随机选边"
    finally:
        settings.BOT_API_TOKEN = old


def test_result_lock_requires_round_complete(admin_client):
    """需求 4：lock=true 仅当本轮全部真实对局结束后才接受（中途锁定 400）。"""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 4)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    round1 = [m for m in _get_matches(admin_client, comp_id) if m["round_id"] == 1]
    assert len(round1) == 2  # 4 人瑞士轮第 1 轮 = 2 场真实对局

    _as_user(admin_client, referee_token)
    # 只打完一场就提交 lock：本轮未结束 -> 400。
    first = round1[0]
    assert admin_client.post(f"/api/matches/{first['id']}/start", json={}).status_code == 200
    resp = admin_client.post(
        f"/api/matches/{first['id']}/result",
        json={"winner": first["participant_a"], "is_draw": False, "score_a": 10, "score_b": 5, "lock": True},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "本轮尚未全部结束，无法锁定结果"

    # 全部打完（不锁定），本轮结束后再提交 lock：允许并锁定。
    second = round1[1]
    assert admin_client.post(f"/api/matches/{second['id']}/start", json={}).status_code == 200
    for m, w in ((first, first["participant_a"]), (second, second["participant_a"])):
        resp = admin_client.post(
            f"/api/matches/{m['id']}/result",
            json={"winner": w, "is_draw": False, "score_a": 1, "score_b": 0},
        )
        assert resp.status_code == 200, resp.text
    resp = admin_client.post(
        f"/api/matches/{first['id']}/result",
        json={"winner": first["participant_a"], "is_draw": False, "score_a": 1, "score_b": 0, "lock": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["result_locked"] is True

    # 锁定后任何修改都被拒绝。
    resp2 = admin_client.post(
        f"/api/matches/{first['id']}/result",
        json={"winner": first["participant_b"], "is_draw": False, "score_a": 3, "score_b": 7},
    )
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "结果已锁定，无法更改"


def test_round_lock_endpoint(admin_client):
    """需求 4：POST /rounds/{round_id}/lock 一键锁定整轮。"""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 4)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    round1 = [m for m in _get_matches(admin_client, comp_id) if m["round_id"] == 1]
    _as_user(admin_client, referee_token)
    # 未打完 -> 400。
    resp = admin_client.post(f"/api/competitions/{comp_id}/rounds/1/lock", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "本轮尚未全部结束，无法锁定结果"

    for m in round1:
        assert admin_client.post(f"/api/matches/{m['id']}/start", json={}).status_code == 200
        resp = admin_client.post(
            f"/api/matches/{m['id']}/result",
            json={"winner": m["participant_a"], "is_draw": False, "score_a": 1, "score_b": 0},
        )
        assert resp.status_code == 200, resp.text
    # 打完 -> 整轮锁定。
    resp = admin_client.post(f"/api/competitions/{comp_id}/rounds/1/lock", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["locked"] == 2
    for m in round1:
        detail = admin_client.get(f"/api/matches/{m['id']}").json()
        assert detail["match"]["result_locked"] is True


def test_complete_round_only_latest_allowed(admin_client):
    """需求 4：complete_round 只允许结束最新一轮（补锁旧轮 400）。"""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 4)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    round1 = [m for m in _get_matches(admin_client, comp_id) if m["round_id"] == 1]
    _as_user(admin_client, referee_token)
    for m in round1:
        assert admin_client.post(f"/api/matches/{m['id']}/start", json={}).status_code == 200
        assert (
            admin_client.post(
                f"/api/matches/{m['id']}/result",
                json={"winner": m["participant_a"], "is_draw": False, "score_a": 1, "score_b": 0},
            ).status_code
            == 200
        )
    # 结束第 1 轮 -> 第 2 轮物化，此时第 1 轮不再是「最新一轮」。
    resp = admin_client.post(f"/api/competitions/{comp_id}/rounds/1/complete", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["next_round_id"] == 2

    # 再次补锁第 1 轮 -> 400。
    resp = admin_client.post(f"/api/competitions/{comp_id}/rounds/1/complete", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "只能结束最新一轮"


def test_reset_latest_round(admin_client):
    """需求 4：POST /rounds/latest/reset 重置最新一轮；排行榜按新赛程重算。"""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    round1 = [m for m in _get_matches(admin_client, comp_id) if m["round_id"] == 1]
    assert len(round1) == 3

    _as_user(admin_client, referee_token)
    # 打完一场（第一场真实结果落地，排行榜不再是全 0）。
    m = round1[0]
    assert admin_client.post(f"/api/matches/{m['id']}/start", json={}).status_code == 200
    assert (
        admin_client.post(
            f"/api/matches/{m['id']}/result",
            json={"winner": m["participant_a"], "is_draw": False, "score_a": 2, "score_b": 1},
        ).status_code
        == 200
    )

    # 重置最新一轮：删除第 1 轮全部对局并重新生成。
    resp = admin_client.post(f"/api/competitions/{comp_id}/rounds/latest/reset", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["round_id"] == 1
    assert resp.json()["match_count"] == 3

    matches = _get_matches(admin_client, comp_id)
    assert len(matches) == 3
    assert all(x["status"] == "pending" for x in matches if x["participant_b"] is not None)

    # 排行榜回到全 0（无任何真实结果）。
    rankings = admin_client.get(f"/api/rankings/competition/{comp_id}").json()
    assert all(row["wins"] == 0 and row["points"] == 0 for row in rankings)


def test_reset_round_refused_when_locked(admin_client):
    """需求 4：最新一轮存在已锁定结果时重置返回 400。

    瑞士轮打完一轮会自动物化下一轮（最新轮变成 pending 新轮），因此用
    单败淘汰（完整赛程排表时已物化，末轮即决赛）构造「已锁定仍是最新轮」。
    """
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(
        admin_client,
        tournament_format="single_elim",
        format_config={},
        max_participants=2,
        referee_ids=[referee_id],
    )
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    _seed_players_and_approve(admin_client, admin_token, comp_id, 2)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200

    matches = _get_matches(admin_client, comp_id)
    assert len(matches) == 1  # 2 人单败 = 1 场决赛（round 1）
    final = matches[0]
    _as_user(admin_client, referee_token)
    assert admin_client.post(f"/api/matches/{final['id']}/start", json={}).status_code == 200
    assert (
        admin_client.post(
            f"/api/matches/{final['id']}/result",
            json={"winner": final["participant_a"], "is_draw": False, "score_a": 1, "score_b": 0},
        ).status_code
        == 200
    )
    assert (
        admin_client.post(f"/api/competitions/{comp_id}/rounds/1/lock", json={}).status_code
        == 200
    )

    resp = admin_client.post(f"/api/competitions/{comp_id}/rounds/latest/reset", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "本轮已有锁定结果，无法重置"


def test_list_matches_public_without_login(client):
    """赛程列表公开只读：未登录也能查看（比赛详情页赛程图依赖它）。"""
    with SessionLocal() as db:
        comp = Competition(name="未认证比赛", status="ongoing", created_by=1)
        db.add(comp)
        db.commit()
        comp_id = comp.id
    resp = client.get(f"/api/competitions/{comp_id}/matches")
    assert resp.status_code == 200
    assert resp.json() == []


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
