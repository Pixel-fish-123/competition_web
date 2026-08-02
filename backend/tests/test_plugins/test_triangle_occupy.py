"""TDD tests for triangle_occupy gameplay plugin (todo 13): unit tests calling
the plugin directly (no HTTP) + a couple through the registry routes.

QA 场景:
- happy: 创建会话(song_lib) -> referee occupy -> admin end（胜者映射回选手）
- failure: 缺 song_lib 400、非本局选手操作 400、<23 首 400、选手操作 403

覆盖 Metis E9（会话恢复时钟）：活实例丢失时 submit_result 走
_restore_controller，elapsed 不跳变。
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.user import User
from app.plugins.triangle_occupy import plugin as plugin_mod
from app.plugins.triangle_occupy.plugin import TriangleOccupyPlugin

PASSWORD = "secret123"
PREFIX = "/api/gameplay/triangle_occupy"

# demo 在仓库外（D:/myproject1/demo）：优先读 demo/test_songs.json，缺失时
# 回退到内嵌的 ≥23 首合法曲库（保证测试自包含、不依赖外部目录）。
DEMO_SONGS_PATH = Path(__file__).resolve().parents[3].parent / "demo" / "test_songs.json"


def _load_song_lib() -> dict:
    if DEMO_SONGS_PATH.is_file():
        return json.loads(DEMO_SONGS_PATH.read_text(encoding="utf-8"))
    types = ["Glitch", "Chaos", "Hard"]
    levels = ["8", "9", "10", "11", "12", "13", "14", "15", "15+", "16"]
    return {
        "songs": [
            {"name": f"Demo Song {i}", "type": types[i % 3], "level": levels[i % len(levels)]}
            for i in range(30)
        ]
    }


SONG_LIB = _load_song_lib()


def _config(song_lib: dict | None = None, **overrides) -> dict:
    cfg: dict = {
        "song_lib": SONG_LIB if song_lib is None else song_lib,
        "sides": {101: "defender", 102: "attacker"},
    }
    cfg.update(overrides)
    return cfg


# ---------------------------------------------------------------------------
# 单元测试：直接调用插件（不经 HTTP）
# ---------------------------------------------------------------------------


@pytest.fixture()
def plugin() -> TriangleOccupyPlugin:
    return TriangleOccupyPlugin()


def test_create_session_valid_song_lib(plugin):
    state = plugin.create_session(1, _config())
    cs = state["controller_state"]
    assert len(cs["board"]) == 27
    assert cs["scores"] == {"defender": 0.0, "attacker": 0.0}
    assert cs["time_limit"] == 25.0
    assert state["sides"] == {101: "defender", 102: "attacker"}
    assert len(state["cells_data"]) == 21
    assert state["elapsed_minutes"] < 1.0
    # 状态必须可 JSON 序列化（POST /session 原样返回）
    json.dumps(state)


def test_create_session_default_sides(plugin):
    state = plugin.create_session(1, {"song_lib": SONG_LIB})
    assert state["sides"] == {"participant_a": "defender", "participant_b": "attacker"}


def test_create_session_normalizes_string_participant_keys(plugin):
    # JSON 对象键经 HTTP 后是字符串；路由层 participant_id 是 int，必须对齐。
    state = plugin.create_session(
        1, {"song_lib": SONG_LIB, "sides": {"101": "defender", "102": "attacker"}}
    )
    assert state["sides"] == {101: "defender", 102: "attacker"}


def test_create_session_missing_song_lib(plugin):
    with pytest.raises(ValueError, match="歌曲库缺失或格式错误"):
        plugin.create_session(1, {})


def test_create_session_invalid_song_lib_format(plugin):
    with pytest.raises(ValueError, match="歌曲库缺失或格式错误"):
        plugin.create_session(1, {"song_lib": {"songs": "not-a-list"}})
    with pytest.raises(ValueError, match="歌曲库缺失或格式错误"):
        plugin.create_session(1, {"song_lib": {"nope": 1}})


def test_create_session_too_few_songs(plugin):
    few = {"songs": [{"name": f"S{i}", "type": "Hard", "level": "12"} for i in range(5)]}
    with pytest.raises(ValueError, match="至少需要 23 首"):
        plugin.create_session(1, {"song_lib": few})


def test_submit_result_occupy(plugin):
    state = plugin.create_session(1, _config())
    new_state = plugin.submit_result(
        1, state, 101, {"action": "occupy", "cell_id": 1, "score": 90}
    )
    assert new_state["last_action"]["ok"] is True
    assert new_state["last_action"]["cell_id"] == 1
    assert new_state["controller_state"]["board"][1]["owner"] == "defender"
    assert new_state["controller_state"]["scores"]["defender"] > 0
    assert new_state["controller_state"]["scores"]["attacker"] == 0.0


def test_submit_result_non_participant(plugin):
    state = plugin.create_session(1, _config())
    with pytest.raises(ValueError, match="非本局参与者"):
        plugin.submit_result(1, state, 999, {"action": "occupy", "cell_id": 1, "score": 90})


def test_submit_result_invalid_cell_id(plugin):
    state = plugin.create_session(1, _config())
    with pytest.raises(ValueError, match="非法格子 ID"):
        plugin.submit_result(1, state, 101, {"action": "occupy", "cell_id": 21, "score": 90})
    with pytest.raises(ValueError, match="非法格子 ID"):
        plugin.submit_result(1, state, 101, {"action": "cancel", "cell_id": -1})


def test_submit_result_cancel(plugin):
    state = plugin.create_session(1, _config())
    state = plugin.submit_result(1, state, 101, {"action": "occupy", "cell_id": 1, "score": 90})
    assert state["controller_state"]["board"][1]["owner"] == "defender"
    state = plugin.submit_result(1, state, 101, {"action": "cancel", "cell_id": 1})
    assert state["last_action"]["ok"] is True
    assert state["controller_state"]["board"][1]["owner"] is None


def test_submit_result_set_time(plugin):
    state = plugin.create_session(1, _config())
    new_state = plugin.submit_result(1, state, 101, {"action": "set_time", "minutes": 10})
    assert new_state["last_action"]["ok"] is True
    assert new_state["controller_state"]["time_limit"] == 10.0


def test_occupy_l1_challenge_failed_detected(plugin):
    state = plugin.create_session(1, _config())
    state = plugin.submit_result(1, state, 101, {"action": "occupy", "cell_id": 0, "score": 80})
    assert state["controller_state"]["board"][0]["owner"] == "defender"
    # 进攻方以更低的 score 挑战 L1：owner 未易主 -> challenge_failed=True
    state = plugin.submit_result(1, state, 102, {"action": "occupy", "cell_id": 0, "score": 70})
    assert state["last_action"]["challenge_failed"] is True
    assert state["controller_state"]["board"][0]["owner"] == "defender"


def test_validate_result(plugin):
    state = plugin.create_session(1, _config())
    assert plugin.validate_result(1, state, 101, {"action": "occupy", "cell_id": 5, "score": 90}) is True
    assert plugin.validate_result(1, state, 102, {"action": "cancel", "cell_id": 3}) is True
    assert plugin.validate_result(1, state, 101, {"action": "reoccupy", "cell_id": 3}) is True
    assert plugin.validate_result(1, state, 101, {"action": "set_time", "minutes": 10}) is True
    # 非法 action 名
    assert plugin.validate_result(1, state, 101, {"action": "bogus"}) is False
    # 非本局选手
    assert plugin.validate_result(1, state, 999, {"action": "occupy", "cell_id": 1}) is False
    # cell_id 越界
    assert plugin.validate_result(1, state, 101, {"action": "occupy", "cell_id": 21}) is False
    assert plugin.validate_result(1, state, 101, {"action": "cancel", "cell_id": -1}) is False
    # time_limit 为负
    assert plugin.validate_result(1, state, 101, {"action": "set_time", "minutes": -5}) is False


def test_end_session_winner_mapped_to_participant(plugin):
    state = plugin.create_session(1, _config())
    # 防守方占 1 格；进攻方占满其余 19 格 -> 进攻方大比分胜
    state = plugin.submit_result(1, state, 101, {"action": "occupy", "cell_id": 1, "score": 90})
    for cid in range(2, 21):
        state = plugin.submit_result(1, state, 102, {"action": "occupy", "cell_id": cid, "score": 0})
    result = plugin.end_session(1, state)
    assert result["is_draw"] is False
    assert result["winner"] == 102
    assert result["score_a"] > 0 and result["score_b"] > result["score_a"]


def test_end_session_draw(plugin):
    state = plugin.create_session(1, _config())
    result = plugin.end_session(1, state)
    assert result["is_draw"] is True
    assert result["winner"] is None
    assert result["score_a"] == 0.0 and result["score_b"] == 0.0


def test_submit_result_restores_controller_when_live_instance_missing(plugin):
    """Metis E9：活实例丢失（重启/DB 恢复）时走 _restore_controller，时钟不跳变。"""
    state = plugin.create_session(1, _config())
    # 模拟对局已进行 5 分钟时持久化
    state["elapsed_minutes"] = 5.0
    # 活实例消失（等价于删掉 state["_controller"]；todo 14 DB 恢复场景）
    plugin_mod._CONTROLLERS.pop(id(state), None)
    new_state = plugin.submit_result(
        1, state, 101, {"action": "occupy", "cell_id": 1, "score": 90}
    )
    # 时钟修复：elapsed ≈ 5 分钟（既不归零也不暴涨）
    assert 4.5 <= new_state["elapsed_minutes"] <= 6.0
    assert new_state["last_action"]["ok"] is True


def test_get_state_returns_public_view(plugin):
    state = plugin.create_session(1, _config())
    view = plugin.get_state(1, state)
    assert view["match_id"] == 1
    assert view["sides"] == {101: "defender", 102: "attacker"}
    assert len(view["controller_state"]["board"]) == 27
    assert view["game_over"] is False
    assert view["elapsed_minutes"] < 1.0
    # 公开视图不泄漏内部字段
    assert "_controller" not in view
    json.dumps(view)


# ---------------------------------------------------------------------------
# HTTP 路由测试（经注册表 + lifespan 挂载的真实路由）
# ---------------------------------------------------------------------------


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


@pytest.fixture()
def users() -> dict:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app):
        yield {
            "admin": _role_client("to_admin", "admin"),
            "referee": _role_client("to_referee", "referee"),
            "player": _role_client("to_player", "player"),
        }


def _http_create(users: dict, config: dict | None = None) -> int:
    resp = users["admin"].post(
        f"{PREFIX}/session", json={"match_id": 1, "config": config or _config()}
    )
    assert resp.status_code == 200
    return resp.json()["session_id"]


def test_http_happy_chain(users):
    sid = _http_create(users)
    # 选手只读状态
    resp = users["player"].get(f"{PREFIX}/session/{sid}/state")
    assert resp.status_code == 200
    assert len(resp.json()["state"]["controller_state"]["board"]) == 27
    # referee 代表选手 101 占领
    resp = users["referee"].post(
        f"{PREFIX}/session/{sid}/action",
        json={"participant_id": 101, "payload": {"action": "occupy", "cell_id": 1, "score": 90}},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # admin 结束对局，胜者映射回选手
    resp = users["admin"].post(f"{PREFIX}/session/{sid}/end")
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["is_draw"] is False
    assert result["winner"] == 101
    assert result["score_a"] > 0


def test_http_player_action_forbidden(users):
    sid = _http_create(users)
    resp = users["player"].post(
        f"{PREFIX}/session/{sid}/action",
        json={"participant_id": 101, "payload": {"action": "occupy", "cell_id": 1, "score": 90}},
    )
    assert resp.status_code == 403


def test_http_missing_song_lib_400(users):
    resp = users["admin"].post(f"{PREFIX}/session", json={"match_id": 1, "config": {}})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "歌曲库缺失或格式错误"


def test_http_few_songs_400(users):
    few = {"songs": [{"name": f"S{i}", "type": "Hard", "level": "12"} for i in range(5)]}
    resp = users["admin"].post(f"{PREFIX}/session", json={"match_id": 1, "config": {"song_lib": few}})
    assert resp.status_code == 400
    assert "23" in resp.json()["detail"]


def test_http_non_participant_action_400(users):
    sid = _http_create(users)
    resp = users["referee"].post(
        f"{PREFIX}/session/{sid}/action",
        json={"participant_id": 999, "payload": {"action": "occupy", "cell_id": 1, "score": 90}},
    )
    assert resp.status_code == 400
