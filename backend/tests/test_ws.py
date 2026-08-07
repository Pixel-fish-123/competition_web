"""TDD tests for the WebSocket match-state subscription endpoint (todo 15).

Covered:
- Metis E13 subscription whitelist: unauthenticated -> 4401; non-participant /
  non-referee / non-admin -> 1008; participant / referee / admin allowed.
- Initial state frame on connect ({"type": "no_session"} when not started;
  {"type": "match_started", ...} when the match is in_progress).
- Broadcast hooks: start_match (match_service) pushes match_started; result
  recording pushes score_update to all subscribed clients.
- Rate limit: > 10 client messages within 1s closes the connection (1008).

The TestClient shares one portal/event loop for all HTTP + WebSocket
sessions, so a broadcast queued by a sync HTTP route is delivered to
concurrently-connected WS clients on the same loop.
"""

import pytest
from starlette.websockets import WebSocketDisconnect

from app.db import SessionLocal
from app.models.registration import Registration

PASSWORD = "secret123"

BASE_PAYLOAD = {
    "name": "WS 测试比赛",
    "description": "对局状态订阅测试",
    "participant_type": "individual",
    "tournament_format": "swiss",
    "referee_ids": [],
    "max_participants": 6,
}


# ------------------------------------------------------------------ helpers


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
    resp = admin_client.post(
        f"/api/competitions/{competition_id}/status", json={"status": status}
    )
    assert resp.status_code == 200, resp.text
    return resp


def _seed_players_and_approve(client, admin_token, competition_id, count):
    """Register ``count`` players and approve them; return [(id, token), ...]."""
    players = []
    for i in range(count):
        pid, ptoken = _register(client, f"player_{i}", f"player{i}@example.com")
        players.append((pid, ptoken))
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
    return players


def _setup_match(admin_client):
    """Create a round-robin competition (6 players, 1 referee) -> ongoing;
    returns (competition_id, first_match, referee_token, players)."""
    admin_token = admin_client.cookies.get("token")
    referee_id, referee_token = _make_referee(admin_client, admin_token)
    comp_id = _create_ok(admin_client, referee_ids=[referee_id])
    assert _transition(admin_client, comp_id, "registration").status_code == 200
    players = _seed_players_and_approve(admin_client, admin_token, comp_id, 6)
    assert _transition(admin_client, comp_id, "ongoing").status_code == 200
    matches = admin_client.get(f"/api/competitions/{comp_id}/matches").json()
    assert matches, "no matches scheduled"
    return comp_id, matches[0], referee_token, players


def _ws_connect(client, match_id, token):
    """Connect a WS client with an explicit cookie header (TestClient's cookie
    jar is cleared first so the header is the only credential source)."""
    client.cookies.clear()
    return client.websocket_connect(
        f"/ws/matches/{match_id}", headers={"cookie": f"token={token}"}
    )


# ------------------------------------------------------------------ rejection


def test_ws_unauthenticated_rejected_with_4401(client):
    # No cookie at all -> 4401 (WS analog of HTTP 401).
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/matches/1"):
            pass
    assert exc.value.code == 4401


def test_ws_non_participant_rejected_with_1008(admin_client):
    _, match, _, players = _setup_match(admin_client)
    assert players
    _, lurker_token = _register(admin_client, "lurker", "lurker@example.com")
    with pytest.raises(WebSocketDisconnect) as exc:
        with _ws_connect(admin_client, match["id"], lurker_token):
            pass
    assert exc.value.code == 1008


def test_ws_unknown_match_rejected_with_1008(admin_client):
    admin_token = admin_client.cookies.get("token")
    with pytest.raises(WebSocketDisconnect) as exc:
        with _ws_connect(admin_client, 99999, admin_token):
            pass
    assert exc.value.code == 1008


# ------------------------------------------------------------------ allowed


def test_ws_participant_connects_and_receives_no_session(admin_client):
    _, match, _, players = _setup_match(admin_client)
    # First round-robin match pairs the two lowest participant ids.
    participant_id, participant_token = players[0]
    assert participant_id in (match["participant_a"], match["participant_b"])
    with _ws_connect(admin_client, match["id"], participant_token) as ws:
        frame = ws.receive_json()
        assert frame["type"] == "no_session"


def test_ws_referee_connects(admin_client):
    _, match, referee_token, _ = _setup_match(admin_client)
    with _ws_connect(admin_client, match["id"], referee_token) as ws:
        frame = ws.receive_json()
        assert frame["type"] in ("no_session", "match_started")


def test_ws_admin_connects(admin_client):
    _, match, _, _ = _setup_match(admin_client)
    admin_token = admin_client.cookies.get("token")
    with _ws_connect(admin_client, match["id"], admin_token) as ws:
        frame = ws.receive_json()
        assert frame["type"] in ("no_session", "match_started")


# ------------------------------------------------------------------ broadcasts


def test_ws_participant_receives_broadcast_when_referee_starts_match(admin_client):
    """start_match (match_service) broadcasts match_started to subscribers."""
    _, match, referee_token, _ = _setup_match(admin_client)

    with _ws_connect(admin_client, match["id"], referee_token) as referee_ws:
        first = referee_ws.receive_json()
        assert first["type"] == "no_session"

        _as_user(admin_client, referee_token)
        resp = admin_client.post(f"/api/matches/{match['id']}/start", json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "in_progress"

        frame = referee_ws.receive_json()
        assert frame == {"type": "match_started", "match_id": match["id"]}


def test_ws_participant_receives_match_started_initial_frame_when_in_progress(
    admin_client,
):
    """对局进行中连接 WS -> 初始帧直接是 match_started（无需先 no_session）。"""
    _, match, referee_token, _ = _setup_match(admin_client)
    _as_user(admin_client, referee_token)
    resp = admin_client.post(f"/api/matches/{match['id']}/start", json={})
    assert resp.status_code == 200, resp.text

    with _ws_connect(admin_client, match["id"], referee_token) as ws:
        frame = ws.receive_json()
        assert frame == {"type": "match_started", "match_id": match["id"]}


def test_ws_participant_receives_score_update_when_referee_records_result(
    admin_client,
):
    """record_match_result 广播 score_update（含最终比分）给订阅者。"""
    _, match, referee_token, _ = _setup_match(admin_client)
    _as_user(admin_client, referee_token)
    resp = admin_client.post(f"/api/matches/{match['id']}/start", json={})
    assert resp.status_code == 200, resp.text

    with _ws_connect(admin_client, match["id"], referee_token) as ws:
        first = ws.receive_json()
        assert first["type"] == "match_started"

        # _ws_connect 清空了 cookie jar，POST 前重新以裁判身份登录。
        _as_user(admin_client, referee_token)
        resp = admin_client.post(
            f"/api/matches/{match['id']}/result",
            json={"winner": match["participant_a"], "score_a": 85.0, "score_b": 72.0},
        )
        assert resp.status_code == 200, resp.text

        frame = ws.receive_json()
        assert frame["type"] == "score_update"
        assert frame["match_id"] == match["id"]
        assert frame["status"] == "finished"
        assert frame["result"]["score_a"] == 85.0
        assert frame["result"]["winner"] == match["participant_a"]


# ------------------------------------------------------------------ rate limit


def test_ws_rate_limit_closes_connection(admin_client):
    _, match, referee_token, _ = _setup_match(admin_client)
    with _ws_connect(admin_client, match["id"], referee_token) as ws:
        ws.receive_json()  # initial state
        # 11 text messages within 1s exceeds the 10/s cap.
        for _ in range(11):
            try:
                ws.send_text("ping")
            except Exception:
                break
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008
