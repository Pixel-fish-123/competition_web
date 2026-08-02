"""TDD tests for the WebSocket match-state subscription endpoint (todo 15).

Covered:
- Metis E13 subscription whitelist: unauthenticated -> 4401; non-participant /
  non-referee / non-admin -> 1008; participant / referee / admin allowed.
- Initial state frame on connect ({"type": "no_session"} when not started;
  {"type": "state_update", ...} when a session exists).
- Broadcast hooks: start_match (match_service) and gameplay action
  (plugin routes) push state_update to all subscribed clients.
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


@pytest.fixture(autouse=True)
def _clean_plugin_session_state():
    """清除跨测试残留的插件内存会话与活控制器。

    玩法的 ``_CONTROLLERS`` 按 ``id(state)`` 索引且 state 仅在会话存活期
    被引用：DB 会话路径（start_match）返回后 state 即失去引用，id 可被复用，
    残留控制器会让后续测试取到陈旧棋盘。``_sessions`` 同理会跨测试累积
    同 match_id 的过期条目。测试前/后各清一次，保证随机顺序下互不串扰。
    """
    import app.plugins.routes as plugin_routes
    import app.plugins.triangle_occupy.plugin as tri_plugin

    plugin_routes._sessions.clear()
    tri_plugin._CONTROLLERS.clear()
    yield
    plugin_routes._sessions.clear()
    tri_plugin._CONTROLLERS.clear()
SONG_LIB = {
    "songs": [
        {"name": f"歌曲{i:02d}", "type": "Glitch", "level": f"{i % 10 + 6}"}
        for i in range(1, 24)
    ]
}

BASE_PAYLOAD = {
    "name": "WS 测试比赛",
    "description": "对局状态订阅测试",
    "participant_type": "individual",
    "tournament_format": "round_robin",
    "format_config": {"group_size": 6},
    "points_rule": {"1": 10, "2": 5},
    "gameplay_plugin": "triangle_occupy",
    "song_lib": SONG_LIB,
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
        assert frame["type"] in ("no_session", "state_update")


def test_ws_admin_connects(admin_client):
    _, match, _, _ = _setup_match(admin_client)
    admin_token = admin_client.cookies.get("token")
    with _ws_connect(admin_client, match["id"], admin_token) as ws:
        frame = ws.receive_json()
        assert frame["type"] in ("no_session", "state_update")


# ------------------------------------------------------------------ broadcasts


def test_ws_participant_receives_broadcast_when_referee_starts_match(admin_client):
    """start_match (match_service) broadcasts state_update to subscribers."""
    _, match, referee_token, _ = _setup_match(admin_client)

    with _ws_connect(admin_client, match["id"], referee_token) as referee_ws:
        first = referee_ws.receive_json()
        assert first["type"] == "no_session"

        _as_user(admin_client, referee_token)
        resp = admin_client.post(f"/api/matches/{match['id']}/start", json={})
        assert resp.status_code == 200, resp.text
        session_id = resp.json()["session_id"]
        assert session_id is not None

        frame = referee_ws.receive_json()
        assert frame["type"] == "state_update"
        assert frame["session_id"] == session_id
        assert "state" in frame


def test_ws_broadcast_state_change_to_two_clients(admin_client):
    """A gameplay action through the plugin routes pushes state_update to all
    subscribers of that match."""
    _, match, referee_token, players = _setup_match(admin_client)

    # Create an in-memory gameplay session via the plugin route.
    _as_user(admin_client, referee_token)
    config = {
        "song_lib": SONG_LIB,
        "seed": 1,
        "sides": {
            match["participant_a"]: "defender",
            match["participant_b"]: "attacker",
        },
    }
    resp = admin_client.post(
        "/api/gameplay/triangle_occupy/session",
        json={"match_id": match["id"], "config": config},
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]

    participant = match["participant_a"]
    _, p_token = next(p for p in players if p[0] == participant)
    with _ws_connect(admin_client, match["id"], referee_token) as ref_ws:
        ref_first = ref_ws.receive_json()
        assert ref_first["type"] == "state_update"
        assert ref_first["session_id"] == session_id

        with _ws_connect(admin_client, match["id"], p_token) as p_ws:
            p_first = p_ws.receive_json()
            assert p_first["type"] == "state_update"
            assert p_first["session_id"] == session_id

            # Trigger a gameplay action as the referee.
            _as_user(admin_client, referee_token)
            resp = admin_client.post(
                f"/api/gameplay/triangle_occupy/session/{session_id}/action",
                json={
                    "participant_id": participant,
                    "payload": {"action": "occupy", "cell_id": 1},
                },
            )
            assert resp.status_code == 200, resp.text

            frame_ref = ref_ws.receive_json()
            frame_p = p_ws.receive_json()
            assert frame_ref["type"] == "state_update"
            assert frame_ref["session_id"] == session_id
            assert frame_ref["state"]["controller_state"]["board"][1]["owner"] == "defender"
            assert frame_p == frame_ref


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
