"""TDD tests for triangle_occupy gameplay plugin (todo 13): unit tests calling
the plugin directly (no HTTP).

玩法路由已从对局流程解耦（matches 不再挂载 /api/gameplay/*），这里保留插件
纯逻辑的单元测试作为参考/未来复用；原 HTTP 路由测试随路由下线一并移除。

QA 场景:
- happy: 创建会话(song_lib) -> referee occupy -> admin end（胜者映射回选手）
- failure: 缺 song_lib 400、非本局选手操作 400、<23 首 400、选手操作 403

覆盖 Metis E9（会话恢复时钟）：活实例丢失时 submit_result 走
_restore_controller，elapsed 不跳变。
"""

import json
from pathlib import Path

import pytest

from app.plugins.triangle_occupy import plugin as plugin_mod
from app.plugins.triangle_occupy.plugin import TriangleOccupyPlugin

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


def test_restore_controller_keeps_board_progress_and_result(plugin):
    """Metis E9 + todo 14 DB 桥：恢复时保留已占领进度/比分/胜负（重连不丢盘）。"""
    state = plugin.create_session(1, _config())
    # 防守方占领 L1(score=80) + L2 格1，模拟对局已有进度
    state = plugin.submit_result(1, state, 101, {"action": "occupy", "cell_id": 0, "score": 80})
    state = plugin.submit_result(1, state, 101, {"action": "occupy", "cell_id": 1, "score": 90})
    progress = state["controller_state"]
    assert progress["board"][1]["owner"] == "defender"
    # 活实例丢失（重启/DB 恢复场景）
    plugin_mod._CONTROLLERS.pop(id(state), None)
    restored = plugin._restore_controller(state)
    # 棋盘进度保留：L1 归属 + 已占格 owner + 比分
    assert restored.cells[0].owner == "defender"
    assert restored.cells[1].owner == "defender"
    assert restored.l1_high_score == 80
    assert restored.defender_score > 0
    # 恢复后的控制器可正常收局，胜者映射回选手
    state2 = dict(state)
    state2["controller_state"] = restored.to_state_dict()
    result = plugin.end_session(1, state2)
    assert result["is_draw"] is False
    assert result["winner"] == 101  # defender -> participant 101


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
