"""Fake gameplay plugin fixture（todo 12 测试用）：实现所有抽象方法的最小插件。

同时作为可被 discover_plugins 加载的插件包示例：
- manifest.json: {"name": "fake", "version": "1.0.0"}
- plugin.py: 暴露 ``plugin: GameplayPlugin`` 实例属性

行为约定（供路由测试断言）:
- create_session: config 含 ``forbidden=True`` 时抛 ValueError。
- submit_result: payload 含 ``bad=True`` 时抛 ValueError；含 ``win=True``
  时把 winner 置为 participant_id。
- validate_result: payload 含 ``invalid=True`` 时返回 False。
- end_session: winner 取 state 中的 winner，否则平局。
"""

from app.plugins.base import GameplayPlugin


class FakePlugin(GameplayPlugin):
    name = "fake"
    version = "1.0.0"

    def create_session(self, match_id: int, config: dict) -> dict:
        if config.get("forbidden"):
            raise ValueError("配置禁止字段 forbidden 不能为真")
        return {"match_id": match_id, "turns": 0, "winner": None}

    def get_state(self, session_id: int, state: dict) -> dict:
        return dict(state)

    def submit_result(
        self, session_id: int, state: dict, participant_id: int, payload: dict
    ) -> dict:
        if payload.get("bad"):
            raise ValueError("非法操作")
        new_state = dict(state)
        new_state["turns"] = new_state.get("turns", 0) + 1
        if payload.get("win"):
            new_state["winner"] = participant_id
        return new_state

    def validate_result(
        self, session_id: int, state: dict, participant_id: int, payload: dict
    ) -> bool:
        return not payload.get("invalid", False)

    def end_session(self, session_id: int, state: dict) -> dict:
        return {
            "winner": state.get("winner"),
            "is_draw": state.get("winner") is None,
            "score_a": 0,
            "score_b": 0,
        }


plugin = FakePlugin()
