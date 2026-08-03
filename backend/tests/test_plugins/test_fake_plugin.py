"""TDD tests for gameplay plugin HTTP routes (todo 12): fake plugin mounted
at /api/gameplay/fake/* through the registry + app lifespan.

覆盖 QA 场景:
- happy: admin 创建会话 → referee 提交操作 → admin 结束对局
- failure: player 操作 403、未登录读状态 401、非法操作 400、
  坏配置 400、未知插件/会话 404
"""

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.competition import Competition
from app.models.match import Match
from app.models.user import User
from app.plugins.registry import registry
from tests.test_plugins.fixtures.fake_plugin.plugin import FakePlugin

PASSWORD = "secret123"
FAKE_PREFIX = "/api/gameplay/fake"


@pytest.fixture(scope="session", autouse=True)
def _register_fake_plugin():
    """会话级：把 fake 插件注册进全局注册表一次，供 lifespan 挂载路由。"""
    if "fake" not in registry.names():
        registry.register(FakePlugin())
    yield


def _flip_role(username: str, role: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one()
        user.role = role
        db.commit()


def _role_client(username: str, role: str) -> TestClient:
    """注册用户（auto-login 落 cookie）并直接写库翻转角色。"""
    c = TestClient(app)
    resp = c.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": PASSWORD},
    )
    assert resp.status_code == 200
    _flip_role(username, role)
    return c


@pytest.fixture()
def users() -> dict:
    """Fresh DB + lifespan 运行（挂载 fake 路由），返回 admin/referee/player 客户端。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app):
        users_dict = {
            "admin": _role_client("admin_user", "admin"),
            "referee": _role_client("referee_user", "referee"),
            "player": _role_client("player1", "player"),
        }
        with SessionLocal() as db:
            admin_id = db.query(User).filter(User.username == "admin_user").one().id
            referee_id = db.query(User).filter(User.username == "referee_user").one().id
        # todo 7：玩法路由按比赛级 referee_ids 校验 —— HTTP 测试需一张真实
        # 比赛 + 对局，且把 referee 放进 referee_ids。
        users_dict["match_id"] = _seed_match(admin_id, [referee_id])
        yield users_dict


def _seed_match(admin_id: int, referee_ids: list[int]) -> int:
    """Seed a Competition + in_progress Match so the per-competition referee
    check (todo 7) passes for referee actions in the HTTP tests."""
    with SessionLocal() as db:
        comp = Competition(
            name="fake 路由测试比赛",
            status="ongoing",
            created_by=admin_id,
            referee_ids=referee_ids,
            gameplay_plugin="fake",
        )
        db.add(comp)
        db.flush()
        match = Match(
            competition_id=comp.id,
            round_id=1,
            participant_a=1,
            participant_b=2,
            engine_match_id=1,
            status="in_progress",
        )
        db.add(match)
        db.commit()
        return match.id


def _create_session(users: dict, *, match_id: int | None = None, config: dict | None = None) -> int:
    mid = users["match_id"] if match_id is None else match_id
    resp = users["admin"].post(
        f"{FAKE_PREFIX}/session", json={"match_id": mid, "config": config or {}}
    )
    assert resp.status_code == 200
    return resp.json()["session_id"]


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_happy_chain_admin_create_referee_action_admin_end(users):
    sid = _create_session(users)

    # player 只读：获取状态
    resp = users["player"].get(f"{FAKE_PREFIX}/session/{sid}/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == sid
    assert body["state"]["match_id"] == users["match_id"]

    # referee 提交操作（选手 2 获胜）
    resp = users["referee"].post(
        f"{FAKE_PREFIX}/session/{sid}/action",
        json={"participant_id": 2, "payload": {"win": True}},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["state"]["winner"] == 2

    # admin 结束对局
    resp = users["admin"].post(f"{FAKE_PREFIX}/session/{sid}/end")
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["winner"] == 2
    assert result["is_draw"] is False
    assert {"score_a", "score_b"} <= set(result)

    # 结束的会话已从存储移除
    resp = users["player"].get(f"{FAKE_PREFIX}/session/{sid}/state")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# failure path
# ---------------------------------------------------------------------------


def test_player_action_forbidden(users):
    sid = _create_session(users)
    resp = users["player"].post(
        f"{FAKE_PREFIX}/session/{sid}/action",
        json={"participant_id": 2, "payload": {}},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "权限不足"


def test_player_cannot_create_session(users):
    resp = users["player"].post(
        f"{FAKE_PREFIX}/session", json={"match_id": 1, "config": {}}
    )
    assert resp.status_code == 403


def test_player_cannot_end_session(users):
    sid = _create_session(users)
    resp = users["player"].post(f"{FAKE_PREFIX}/session/{sid}/end")
    assert resp.status_code == 403


def test_unauth_state_401(users):
    sid = _create_session(users)
    resp = TestClient(app).get(f"{FAKE_PREFIX}/session/{sid}/state")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或登录已失效"


def test_invalid_action_validate_false_400(users):
    sid = _create_session(users)
    resp = users["referee"].post(
        f"{FAKE_PREFIX}/session/{sid}/action",
        json={"participant_id": 2, "payload": {"invalid": True}},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "非法操作"


def test_invalid_action_submit_valueerror_400(users):
    sid = _create_session(users)
    resp = users["referee"].post(
        f"{FAKE_PREFIX}/session/{sid}/action",
        json={"participant_id": 2, "payload": {"bad": True}},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "非法操作"


def test_create_session_bad_config_400(users):
    resp = users["admin"].post(
        f"{FAKE_PREFIX}/session",
        json={"match_id": 1, "config": {"forbidden": True}},
    )
    assert resp.status_code == 400
    assert "forbidden" in resp.json()["detail"]


def test_unknown_plugin_404(users):
    resp = users["admin"].post(
        "/api/gameplay/nope/session", json={"match_id": 1, "config": {}}
    )
    assert resp.status_code == 404


def test_unknown_session_404(users):
    resp = users["player"].get(f"{FAKE_PREFIX}/session/9999/state")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "对局会话不存在"
