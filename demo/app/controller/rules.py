from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "rules.json"

_DEFAULT_RULES: dict = {
    "difficulty_score": {
        "15+": 15,
        "15": 10,
        "14": 8,
        "13": 6,
        "12": 5,
        "11": 4,
        "9": 3,
        "8": 2,
    },
    "tasks": [
        {"name": "达成MM", "weight": 2, "bonus": 10},
        {"name": "达成tp99.5以上", "weight": 1, "bonus": 10},
        {"name": "达成99.5w以上", "weight": 1, "bonus": 10},
        {"name": "达成tp99以上", "weight": 2, "bonus": 8},
        {"name": "达成97w以上", "weight": 2, "bonus": 8},
        {"name": "达成tp98以上", "weight": 5, "bonus": 6},
        {"name": "达成95w以上", "weight": 5, "bonus": 6},
        {"name": "达成tp97以上", "weight": 8, "bonus": 4},
        {"name": "达成93w以上", "weight": 8, "bonus": 4},
        {"name": "达成tp96以上", "weight": 8, "bonus": 3},
        {"name": "达成92w以上", "weight": 8, "bonus": 3},
        {"name": "达成tp95以上", "weight": 6, "bonus": 1},
        {"name": "达成91w以上", "weight": 6, "bonus": 1},
        {"name": "达成90w以上", "weight": 6, "bonus": 0},
        {"name": "达成FULL COMBO", "weight": 4, "bonus": 7},
        {"name": "达成miss <= 1, bad <= 1, good <= 1", "weight": 10, "bonus": 5},
    ],
    "templates": {
        "A": {"top": "high", "mid": "medium", "shallow": "low", "energy": "medium"},
        "B": {"top": "medium", "mid": "low", "shallow": "medium", "energy": "high"},
        "C": {"top": "medium", "mid": "high", "shallow": "medium", "energy": "low"},
    },
    # 测试歌曲生成器的难度权重池（level -> 出现权重），移入配置便于后续调整。
    "song_level_weights": {
        "15+": 1, "16": 1, "16+": 1,
        "15": 2, "14+": 2, "14": 2,
        "13+": 3, "13": 3, "12+": 3, "12": 3,
        "11+": 2, "11": 2, "10": 2, "10+": 2,
        "9+": 2, "9": 2, "8": 2,
    },
}


def load_rules() -> dict:
    """Load rules from config/rules.json; fall back to built-in defaults on any failure.

    文件中的键覆盖默认值，未提供的键（如 song_level_weights）由内置默认补齐，
    保证调用方总能取到完整规则集。
    """
    try:
        with open(_RULES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "tasks" not in data or "templates" not in data:
            raise ValueError("missing required keys: tasks, templates")
        merged = dict(_DEFAULT_RULES)
        merged.update({k: v for k, v in data.items() if v is not None})
        return merged
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to load rules from %s (%s); using built-in defaults", _RULES_PATH, exc)
        return dict(_DEFAULT_RULES)


RULES = load_rules()
