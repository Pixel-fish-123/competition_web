"""Random test-song generator for the triangle-occupation controller.

Produces a JSON song library ({"songs": [...]}) that is accepted by
controller.song_lib.parse_song_library. Guarantees unique names and
stratified coverage of all 8 diff-score tiers (15/10/8/6/5/4/3/2).

Usage:
    python tools/gen_test_songs.py [--count N] [--output FILE] [--seed N]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# Import the validator and rule loader from the controller package (project root on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from controller.rules import load_rules  # noqa: E402
from controller.song_lib import parse_song_library  # noqa: E402

PREFIXES = [
    "Neon", "Crimson", "Void", "Stellar", "Phantom", "Chrono", "Azure",
    "Hyper", "Solar", "Crystal", "Obsidian", "Electric", "Silent", "Frozen",
    "Inferno", "Astral",
]
SUFFIXES = [
    "Requiem", "Pulse", "Horizon", "Reverie", "Storm", "Echo", "Nova",
    "Burst", "Mirage", "Symphony", "Sanctum", "Velocity", "Prism", "Rapture",
    "Genesis", "Paradox",
]

# 难度权重池（level -> 权重，中档为主）改由 config/rules.json 提供（song_level_weights）；
# 配置缺失/损坏时回退内置默认，保证工具始终可用。
_DEFAULT_POOL: dict[str, int] = {
    "15+": 1, "16": 1, "16+": 1,
    "15": 2, "14+": 2, "14": 2,
    "13+": 3, "13": 3, "12+": 3, "12": 3,
    "11+": 2, "11": 2, "10": 2, "10+": 2,
    "9+": 2, "9": 2, "8": 2,
}


def _difficulty_pool() -> dict[str, int]:
    """从规则配置读取测试歌曲难度权重池（level -> weight）。"""
    weights = (load_rules().get("song_level_weights") or {})
    pool = {str(lv): int(w) for lv, w in weights.items() if int(w) > 0}
    return pool or dict(_DEFAULT_POOL)

# The 10-scale song-score tiers we must cover, each mapped to a (level, type)
# combo that yields it (level_to_score 10 分制，Chaos/Glitch 在 13/14 档 +1)。
TIER_LEVELS = {
    10: ("15+", "Glitch"),
    9: ("15", "Hard"),
    8: ("14", "Chaos"),
    7: ("13", "Chaos"),
    6: ("12", "Hard"),
    5: ("11", "Hard"),
    4: ("10", "Hard"),
    3: ("8", "Hard"),
}

TYPES = ["Glitch", "Chaos", "Hard"]


def _weighted_pick(pool: dict[str, int], rng: random.Random) -> str:
    """Weighted random pick from a {value: weight} dict."""
    items = list(pool.items())
    total = sum(w for _, w in items)
    r = rng.uniform(0, total)
    upto = 0.0
    for value, weight in items:
        upto += weight
        if upto >= r:
            return value
    return items[-1][0]


def _make_name(rng: random.Random, used: set[str]) -> str:
    """Generate a unique song name from the affix pools."""
    base = f"{rng.choice(PREFIXES)} {rng.choice(SUFFIXES)}"
    if base not in used:
        return base
    # Combo pool exhausted for this base; append a numeric suffix.
    n = 2
    while f"{base} {n}" in used:
        n += 1
    return f"{base} {n}"


def generate_songs(count: int, rng: random.Random) -> list[dict]:
    """Generate `count` songs with unique names and 10-scale tier coverage."""
    songs: list[dict] = []
    used_names: set[str] = set()

    # Stratified guarantee: reserve one song per song-score tier (10 分制 3~10)。
    for tier in (10, 9, 8, 7, 6, 5, 4, 3):
        if len(songs) >= count:
            break
        level, stype = TIER_LEVELS[tier]
        name = _make_name(rng, used_names)
        used_names.add(name)
        songs.append({
            "name": name,
            "type": stype,
            "level": level,
        })

    # Remaining songs: random weighted difficulty (pool from config/rules.json).
    pool = _difficulty_pool()
    while len(songs) < count:
        name = _make_name(rng, used_names)
        used_names.add(name)
        songs.append({
            "name": name,
            "type": rng.choice(TYPES),
            "level": _weighted_pick(pool, rng),
        })

    return songs


def _tiers_covered(songs: list[dict]) -> bool:
    """Check that all 10-scale tiers 3..10 are present."""
    scores = {parse_song_library({"songs": songs})[i].diff_score for i in range(len(songs))}
    return scores == {3, 4, 5, 6, 7, 8, 9, 10}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a random test-song library.")
    parser.add_argument("--count", type=int, default=50, help="number of songs (default 50)")
    parser.add_argument("--output", type=str, default="test_songs.json",
                        help="output JSON file (default test_songs.json)")
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    args = parser.parse_args()

    if args.count < 1:
        print("error: --count must be >= 1", file=sys.stderr)
        return 1

    rng = random.Random(args.seed)

    # Self-check before writing: parseable + 8-tier coverage (skip tier check
    # when fewer than 8 songs). Retry up to 5 times.
    for attempt in range(1, 6):
        songs = generate_songs(args.count, rng)
        try:
            parsed = parse_song_library({"songs": songs})
        except ValueError as exc:
            print(f"attempt {attempt}: parse failed: {exc}", file=sys.stderr)
            continue
        if args.count >= 8 and not _tiers_covered(songs):
            print(f"attempt {attempt}: 8-tier coverage not met", file=sys.stderr)
            continue
        # Success.
        out_path = Path(args.output)
        out_path.write_text(
            json.dumps({"songs": songs}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"wrote {len(songs)} songs to {out_path}")
        return 0

    print("error: failed to generate a valid song library after 5 attempts",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
