"""todo 7: per-competition referee scope on gameplay routes（④A 越权堵漏）。

基线特征（修前失败）：/api/gameplay/<name>/session、/session/{id}/action、
/session/{id}/end 三个端点只做 require_referee（全局角色）校验 —— 任意全局
referee 都能操作任何比赛的玩法会话（越权）。修后：referee 必须在该比赛的
referee_ids 内，admin 始终放行。

覆盖：create_session / submit_action / end_session 三端点 ×
（未指派裁判 403 / 指派裁判 200 / admin 200）；另覆盖 admin 建会、未指派
全局裁判事后操作同一会话仍 403 的对抗场景。
"""

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.competition import Competition
from app.models.match import Match
from app.models.user import User

PASSWORD = "secret123"
PREFIX = "/api/gameplay/triangle_occupy"

# triangle_occupy 要求歌曲库 ≥ 23 首（与 test_matches 同构，保证自包含）。
SONG_LIB = {
    "songs": [
        {"name": f"歌曲{i:02d}", "type": "Glitch", "level": f"{i % 10 + 6}"}
        for i in range(1, 24)
    ]
}


def _flip_role(username: str, role: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one()
        user.role = role
        db.commit()


def _role_client(username: str, role: str) -> TestClient:
    c = TestClient(app)
    resp = c.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": PASSWORD},
    )
    assert resp.status_code == 200
    _flip_role(username, role)
    return c


@pytest.fixture(autouse=True)
def _clean_session_state():
    """清除跨测试残留的插件内存会话与活控制器（与 test_ws 同理由）。"""
    import app.plugins.routes as plugin_routes
    import app.plugins.triangle_occupy.plugin as tri_plugin

    plugin_routes._sessions.clear()
    tri_plugin._CONTROLLERS.clear()
    yield
    plugin_routes._sessions.clear()
    tri_plugin._CONTROLLERS.clear()


@pytest.fixture()
def env() -> dict:
    """Fresh DB：指派比赛（assigned 裁判在 referee_ids）+ 未指派比赛（空裁判
    组），各带一张 in_progress 对局。返回 admin/assigned/outsider 客户端与
    两张对局的信息 (match_id, participant_a, participant_b)。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app):
        admin = _role_client("scope_admin", "admin")
        assigned = _role_client("scope_assigned", "referee")
        outsider = _role_client("scope_outsider", "referee")
        with SessionLocal() as db:
            admin_id = db.query(User).filter(User.username == "scope_admin").one().id
            assigned_id = db.query(User).filter(User.username == "scope_assigned").one().id
            comp_a = Competition(
                name="指派比赛", status="ongoing", created_by=admin_id, referee_ids=[assigned_id]
            )
            db.add(comp_a)
            db.flush()
            match_a = Match(
                competition_id=comp_a.id,
                round_id=1,
                participant_a=101,
                participant_b=102,
                engine_match_id=1,
                status="in_progress",
            )
            db.add(match_a)
            comp_b = Competition(
                name="未指派比赛", status="ongoing", created_by=admin_id, referee_ids=[]
            )
            db.add(comp_b)
            db.flush()
            match_b = Match(
                competition_id=comp_b.id,
                round_id=1,
                participant_a=201,
                participant_b=202,
                engine_match_id=1,
                status="in_progress",
            )
            db.add(match_b)
            db.commit()
            match_a_id, match_b_id = match_a.id, match_b.id
        yield {
            "admin": admin,
            "assigned": assigned,
            "outsider": outsider,
            "assigned_match": (match_a_id, 101, 102),
            "unassigned_match": (match_b_id, 201, 202),
        }


def _config(participants: tuple[int, int]) -> dict:
    p_a, p_b = participants
    return {"song_lib": SONG_LIB, "sides": {p_a: "defender", p_b: "attacker"}}


def _create(env: dict, key: str, role: str, config: dict | None = None) -> int:
    """以指定角色在 key 对局上创建会话，返回 session_id（断言 200）。"""
    match_id, p_a, p_b = env[key]
    resp = env[role].post(
        f"{PREFIX}/session",
        json={"match_id": match_id, "config": config if config is not None else _config((p_a, p_b))},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["session_id"]


# --------------------------------------------------------------- create_session


def test_create_session_outsider_referee_403(env):
    """全局 referee（不在 referee_ids）不能为他人比赛创建会话。"""
    match_id, _, _ = env["unassigned_match"]
    resp = env["outsider"].post(
        f"{PREFIX}/session", json={"match_id": match_id, "config": {}}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "非本场比赛裁判"


def test_create_session_assigned_referee_200(env):
    sid = _create(env, "assigned_match", "assigned")
    assert sid > 0


def test_create_session_admin_on_unassigned_200(env):
    sid = _create(env, "unassigned_match", "admin")
    assert sid > 0


def test_create_session_unknown_match_404(env):
    resp = env["outsider"].post(
        f"{PREFIX}/session", json={"match_id": 99999, "config": {}}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "对局不存在"


# --------------------------------------------------------------- submit_action


def test_submit_action_outsider_referee_403(env):
    sid = _create(env, "assigned_match", "assigned")
    _, p_a, _ = env["assigned_match"]
    resp = env["outsider"].post(
        f"{PREFIX}/session/{sid}/action",
        json={"participant_id": p_a, "payload": {"action": "occupy", "cell_id": 1, "score": 90}},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "非本场比赛裁判"


def test_submit_action_outsider_forbidden_on_admin_created_session(env):
    """对抗：admin 建会，未指派全局裁判事后仍不能操作该会话。"""
    sid = _create(env, "unassigned_match", "admin")
    _, p_a, _ = env["unassigned_match"]
    resp = env["outsider"].post(
        f"{PREFIX}/session/{sid}/action",
        json={"participant_id": p_a, "payload": {"action": "occupy", "cell_id": 1, "score": 90}},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "非本场比赛裁判"


def test_submit_action_assigned_referee_200(env):
    sid = _create(env, "assigned_match", "assigned")
    _, p_a, _ = env["assigned_match"]
    resp = env["assigned"].post(
        f"{PREFIX}/session/{sid}/action",
        json={"participant_id": p_a, "payload": {"action": "occupy", "cell_id": 1, "score": 90}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert resp.json()["state"]["controller_state"]["board"][1]["owner"] == "defender"


def test_submit_action_admin_on_unassigned_200(env):
    sid = _create(env, "unassigned_match", "admin")
    _, p_a, _ = env["unassigned_match"]
    resp = env["admin"].post(
        f"{PREFIX}/session/{sid}/action",
        json={"participant_id": p_a, "payload": {"action": "occupy", "cell_id": 1, "score": 90}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True


# ---------------------------------------------------------------- end_session


def test_end_session_outsider_referee_403(env):
    sid = _create(env, "assigned_match", "assigned")
    resp = env["outsider"].post(f"{PREFIX}/session/{sid}/end")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "非本场比赛裁判"


def test_end_session_outsider_forbidden_on_admin_created_session(env):
    sid = _create(env, "unassigned_match", "admin")
    resp = env["outsider"].post(f"{PREFIX}/session/{sid}/end")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "非本场比赛裁判"


def test_end_session_assigned_referee_200(env):
    sid = _create(env, "assigned_match", "assigned")
    resp = env["assigned"].post(f"{PREFIX}/session/{sid}/end")
    assert resp.status_code == 200, resp.text
    assert resp.json()["session_id"] == sid


def test_end_session_admin_on_unassigned_200(env):
    sid = _create(env, "unassigned_match", "admin")
    resp = env["admin"].post(f"{PREFIX}/session/{sid}/end")
    assert resp.status_code == 200, resp.text
    assert resp.json()["session_id"] == sid
