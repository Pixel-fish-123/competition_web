"""玩法插件注册表（todo 12）：注册、查询与目录扫描加载。

- :class:`PluginRegistry`: 进程内插件注册表（name -> GameplayPlugin）。
- :func:`discover_plugins`: 扫描插件目录，加载含 manifest.json 的子包
  （importlib 动态导入 ``plugin.py``，取其中 ``plugin`` 属性）。
- :func:`register_default_plugins`: 注册默认插件目录下的全部插件，
  供应用启动（main.py lifespan）调用。
- ``registry``: 模块级单例，应用内全局共享。

插件包目录结构约定::

    plugins/
        my_plugin/
            manifest.json   # {"name": ..., "version": ...}
            plugin.py       # 暴露 ``plugin: GameplayPlugin`` 实例属性

仅扫描 ``plugins_dir`` 的直接子目录，绝不加载插件目录自身，也不递归。
无 manifest.json 的目录静默跳过；manifest 缺失 name/version、plugin.py
缺失或格式非法时抛 :class:`ValueError`（带清晰的目录路径信息）。

默认扫描目录可用环境变量 ``GAMEPLAY_PLUGINS_DIR`` 覆盖（测试/部署用）。
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import os
from pathlib import Path

from app.plugins.base import GameplayPlugin

# 默认扫描目录 = 本包所在目录（backend/app/plugins）。
DEFAULT_PLUGINS_DIR = Path(__file__).resolve().parent

_module_seq = itertools.count(1)


class PluginRegistry:
    """name -> GameplayPlugin 的进程内注册表。"""

    def __init__(self) -> None:
        self._plugins: dict[str, GameplayPlugin] = {}

    def register(self, plugin: GameplayPlugin) -> None:
        """注册一个插件；同名插件重复注册抛 ValueError。"""
        if not isinstance(plugin, GameplayPlugin):
            raise TypeError(f"插件必须继承 GameplayPlugin，得到: {type(plugin)!r}")
        if plugin.name in self._plugins:
            raise ValueError(f"插件已注册，名称重复: {plugin.name!r}")
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> GameplayPlugin | None:
        """按名称取插件；未注册返回 None。"""
        return self._plugins.get(name)

    def all(self) -> list[GameplayPlugin]:
        """返回全部已注册插件（按注册顺序）。"""
        return list(self._plugins.values())

    def names(self) -> list[str]:
        """返回全部已注册插件名称（按注册顺序）。"""
        return list(self._plugins)


registry = PluginRegistry()


def _default_plugins_dir() -> Path:
    """默认插件目录，可用环境变量 GAMEPLAY_PLUGINS_DIR 覆盖。"""
    override = os.environ.get("GAMEPLAY_PLUGINS_DIR")
    if override:
        return Path(override)
    return DEFAULT_PLUGINS_DIR


def _load_plugin_package(plugin_dir: Path) -> GameplayPlugin | None:
    """加载一个插件子目录；无 manifest.json 时返回 None（静默跳过）。"""
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.is_file():
        return None

    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"插件 manifest.json 不是合法 JSON: {plugin_dir} ({e})") from e

    name = manifest.get("name")
    version = manifest.get("version")
    if not name or not version:
        raise ValueError(
            f"插件 manifest.json 必须包含非空的 name 和 version 字段: {plugin_dir}"
        )

    plugin_py = plugin_dir / "plugin.py"
    if not plugin_py.is_file():
        raise ValueError(f"插件目录缺少 plugin.py: {plugin_dir}")

    module_name = f"_gameplay_plugin_{name}_{next(_module_seq)}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_py)
    if spec is None or spec.loader is None:
        raise ValueError(f"无法加载插件模块: {plugin_py}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    plugin = getattr(module, "plugin", None)
    if not isinstance(plugin, GameplayPlugin):
        raise ValueError(f"plugin.py 必须暴露 GameplayPlugin 实例属性 'plugin': {plugin_dir}")
    if plugin.name != name:
        raise ValueError(
            f"插件 name 与 manifest 不一致: manifest={name!r}, plugin={plugin.name!r}"
        )
    return plugin


def discover_plugins(plugins_dir: Path | None = None) -> list[GameplayPlugin]:
    """扫描 ``plugins_dir``（默认 backend/app/plugins）下的插件子目录并加载。

    规则:
    - 子目录含 manifest.json（非空 name/version）与 plugin.py
      （暴露 ``plugin`` 实例属性）→ 加载并返回该插件。
    - 无 manifest.json 的目录静默跳过；普通文件忽略。
    - manifest 缺失 name/version、plugin.py 缺失或格式非法 → ValueError。
    - 不扫描 ``plugins_dir`` 自身，也不递归子目录。
    """
    base = Path(plugins_dir) if plugins_dir is not None else _default_plugins_dir()
    if not base.is_dir():
        raise ValueError(f"插件目录不存在: {base}")

    loaded: list[GameplayPlugin] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        plugin = _load_plugin_package(child)
        if plugin is not None:
            loaded.append(plugin)
    return loaded


def register_default_plugins() -> list[GameplayPlugin]:
    """扫描并注册默认插件目录下的全部插件（已注册的同名插件跳过）。

    返回本次发现（并注册）的插件列表。应于应用启动时调用一次；
    重复调用是安全的：已注册名称会被跳过，不会抛重复注册错误。
    """
    plugins = discover_plugins()
    for plugin in plugins:
        if plugin.name in registry._plugins:
            continue
        registry.register(plugin)
    return plugins
