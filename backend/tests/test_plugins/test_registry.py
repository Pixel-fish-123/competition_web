"""TDD tests for the plugin registry (todo 12): register/get/duplicate,
discover_plugins on temp dirs, manifest validation rules."""

import json
import tempfile
from pathlib import Path

import pytest

from app.plugins.base import GameplayPlugin
from app.plugins.registry import PluginRegistry, discover_plugins

END_RESULT = "{'winner': None, 'is_draw': True, 'score_a': 0, 'score_b': 0}"

METHOD_BODY = (
    "    def create_session(self, match_id, config): return {}\n"
    "    def get_state(self, session_id, state): return state\n"
    "    def submit_result(self, session_id, state, participant_id, payload): return state\n"
    "    def validate_result(self, session_id, state, participant_id, payload): return True\n"
    f"    def end_session(self, session_id, state): return {END_RESULT}\n"
)


class DummyPlugin(GameplayPlugin):
    name = "dummy"
    version = "0.1.0"

    def create_session(self, match_id, config):
        return {}

    def get_state(self, session_id, state):
        return state

    def submit_result(self, session_id, state, participant_id, payload):
        return state

    def validate_result(self, session_id, state, participant_id, payload):
        return True

    def end_session(self, session_id, state):
        return {"winner": None, "is_draw": True, "score_a": 0, "score_b": 0}


def _plugin_src(name: str, version: str) -> str:
    return (
        "from app.plugins.base import GameplayPlugin\n"
        f"class P(GameplayPlugin):\n"
        f"    name = {name!r}\n"
        f"    version = {version!r}\n"
        f"{METHOD_BODY}"
        "plugin = P()\n"
    )


def _write_plugin_dir(base: Path, name: str, *, version="1.0.0", src=None) -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(
        json.dumps({"name": name, "version": version}), encoding="utf-8"
    )
    (d / "plugin.py").write_text(src or _plugin_src(name, version), encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# PluginRegistry unit tests
# ---------------------------------------------------------------------------


def test_register_and_get():
    reg = PluginRegistry()
    reg.register(DummyPlugin())
    assert reg.get("dummy") is not None
    assert reg.get("missing") is None
    assert reg.names() == ["dummy"]
    assert reg.all()[0].name == "dummy"


def test_register_duplicate_name_raises_value_error():
    reg = PluginRegistry()
    reg.register(DummyPlugin())
    with pytest.raises(ValueError, match="名称重复"):
        reg.register(DummyPlugin())


def test_register_rejects_non_plugin():
    reg = PluginRegistry()
    with pytest.raises(TypeError, match="GameplayPlugin"):
        reg.register(object())  # type: ignore[arg-type]


def test_registry_singleton_is_shared():
    from app.plugins.registry import registry

    before = list(registry.names())
    registry.register(DummyPlugin())
    try:
        assert registry.get("dummy") is not None
        assert "dummy" in registry.names()
    finally:
        # 清理单例，避免污染其它测试
        registry._plugins.pop("dummy", None)
    assert registry.names() == before


# ---------------------------------------------------------------------------
# discover_plugins
# ---------------------------------------------------------------------------


def test_discover_empty_dir_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        plugins = discover_plugins(Path(tmp))
    assert plugins == []


def test_discover_loads_valid_plugin():
    with tempfile.TemporaryDirectory() as tmp:
        _write_plugin_dir(Path(tmp), "dummy")
        plugins = discover_plugins(Path(tmp))
    assert len(plugins) == 1
    assert plugins[0].name == "dummy"
    assert plugins[0].version == "1.0.0"


def test_discover_directory_without_manifest_skipped_silently():
    with tempfile.TemporaryDirectory() as tmp:
        bare = Path(tmp) / "not_a_plugin"
        bare.mkdir()
        (bare / "random.py").write_text("x = 1\n", encoding="utf-8")
        assert discover_plugins(Path(tmp)) == []


def test_discover_ignores_plain_files():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "stray.txt").write_text("hello", encoding="utf-8")
        assert discover_plugins(Path(tmp)) == []


def test_discover_manifest_missing_version_raises():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "broken"
        d.mkdir()
        (d / "manifest.json").write_text(
            json.dumps({"name": "broken"}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="name 和 version"):
            discover_plugins(Path(tmp))


def test_discover_manifest_missing_name_raises():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "broken"
        d.mkdir()
        (d / "manifest.json").write_text(
            json.dumps({"version": "1.0.0"}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="name 和 version"):
            discover_plugins(Path(tmp))


def test_discover_missing_plugin_py_raises():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "broken"
        d.mkdir()
        (d / "manifest.json").write_text(
            json.dumps({"name": "broken", "version": "1.0.0"}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="plugin.py"):
            discover_plugins(Path(tmp))


def test_discover_missing_plugin_attribute_raises():
    with tempfile.TemporaryDirectory() as tmp:
        _write_plugin_dir(Path(tmp), "dummy", src="x = 1\n")
        with pytest.raises(ValueError, match="'plugin'"):
            discover_plugins(Path(tmp))


def test_discover_loads_fixture_fake_plugin():
    """Fixture 插件包可通过真实扫描机制加载（manifest + plugin.py 契约有效）。"""
    fixtures_dir = Path(__file__).parent / "fixtures"
    plugins = discover_plugins(fixtures_dir)
    assert any(p.name == "fake" and p.version == "1.0.0" for p in plugins)


# ---------------------------------------------------------------------------
# GET /api/admin/plugins
# ---------------------------------------------------------------------------


def test_admin_list_plugins_returns_200(client, admin_client):
    """admin 调 GET /api/admin/plugins 返回 200 与合法列表。

    玩法已从对局流程解耦：lifespan 不再注册默认插件，注册表通常为空；
    端点只负责返回当前已注册项（可能是空列表），不报错。
    """
    resp = admin_client.get("/api/admin/plugins")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    for p in body:
        assert "name" in p and "version" in p


def test_player_list_plugins_forbidden(client):
    """player 调同端点返回 403。"""
    resp = client.post(
        "/api/auth/register",
        json={"username": "player_x", "email": "px@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    resp = client.get("/api/admin/plugins")
    assert resp.status_code == 403
