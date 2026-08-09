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
}


def load_rules() -> dict:
    """Load rules from config/rules.json; fall back to built-in defaults on any failure."""
    try:
        with open(_RULES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "tasks" not in data or "templates" not in data:
            raise ValueError("missing required keys: tasks, templates")
        return data
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to load rules from %s (%s); using built-in defaults", _RULES_PATH, exc)
        return dict(_DEFAULT_RULES)


RULES = load_rules()
