"""规则加载测试：config/rules.json 与内置默认的一致性、缺失回退。

运行：cd demo && python -m pytest tests/test_rules.py -q
"""

import json

import pytest

import controller.rules as rules_mod


def test_default_rules_shape():
    d = rules_mod._DEFAULT_RULES
    assert len(d["tasks"]) == 16
    assert d["tasks"][0]["name"] == "达成MM"
    assert d["tasks"][0]["bonus"] == 10
    assert set(d["templates"].keys()) == {"A", "B", "C"}
    assert set(d["song_level_weights"].keys()) == {
        "15+", "16", "16+", "15", "14+", "14", "13+", "13",
        "12+", "12", "11+", "11", "10", "10+", "9+", "9", "8",
    }


def test_load_rules_matches_file(monkeypatch, tmp_path):
    """加载结果与 config/rules.json 文件内容一致（数据源优先）。"""
    rules = rules_mod.load_rules()
    assert len(rules["tasks"]) == 16
    assert len(rules["templates"]) == 3
    assert len(rules["song_level_weights"]) == 17


def test_load_rules_missing_file_falls_back(monkeypatch, tmp_path):
    """文件缺失 -> 回退内置默认且不抛异常。"""
    monkeypatch.setattr(rules_mod, "_RULES_PATH", tmp_path / "nope.json")
    rules = rules_mod.load_rules()
    assert len(rules["tasks"]) == 16
    assert rules["tasks"][0]["name"] == "达成MM"


def test_load_rules_corrupt_file_falls_back(monkeypatch, tmp_path):
    p = tmp_path / "rules.json"
    p.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(rules_mod, "_RULES_PATH", p)
    rules = rules_mod.load_rules()
    assert len(rules["tasks"]) == 16


def test_load_rules_missing_keys_falls_back(monkeypatch, tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps({"difficulty_score": {}}), encoding="utf-8")
    monkeypatch.setattr(rules_mod, "_RULES_PATH", p)
    rules = rules_mod.load_rules()
    assert len(rules["tasks"]) == 16


def test_file_and_default_in_sync():
    """rules.py 内置默认与 config/rules.json 必须保持一致（H 类硬约束）。"""
    with open(rules_mod._RULES_PATH, encoding="utf-8") as f:
        file_data = json.load(f)
    for key in ("tasks", "templates", "song_level_weights"):
        assert file_data[key] == rules_mod._DEFAULT_RULES[key], key


def test_rules_module_cache():
    assert isinstance(rules_mod.RULES, dict)
    assert len(rules_mod.RULES["tasks"]) == 16
