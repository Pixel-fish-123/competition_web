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

# Import the validator from the controller package (project root on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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

# Weighted difficulty pool, mid-tier heavy.
DIFFICULTY_POOL = [
    ("15+", 1), ("16", 1), ("16+", 1),
    ("15", 2), ("14+", 2), ("14", 2),
    ("13+", 3), ("13", 3), ("12+", 3), ("12", 3),
    ("11+", 2), ("11", 2), ("10", 2), ("10+", 2),
    ("9+", 2), ("9", 2), ("8", 2),
]

# The 8 diff-score tiers we must cover, each mapped to a level that yields it.
TIER_LEVELS = {
    15: "15+",
    10: "15",
    8: "14",
    6: "13",
    5: "12",
    4: "11",
    3: "10",
    2: "8",
}

TYPES = ["Glitch", "Chaos", "Hard"]


def _weighted_pick(pool, rng: random.Random):
    """Weighted random pick from a list of (value, weight) tuples."""
    total = sum(w for _, w in pool)
    r = rng.uniform(0, total)
    upto = 0.0
    for value, weight in pool:
        upto += weight
        if upto >= r:
            return value
    return pool[-1][0]


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
    """Generate `count` songs with unique names and 8-tier coverage."""
    songs: list[dict] = []
    used_names: set[str] = set()

    # Stratified guarantee: reserve one song per diff-score tier.
    for tier in (15, 10, 8, 6, 5, 4, 3, 2):
        if len(songs) >= count:
            break
        name = _make_name(rng, used_names)
        used_names.add(name)
        songs.append({
            "name": name,
            "type": rng.choice(TYPES),
            "level": TIER_LEVELS[tier],
        })

    # Remaining songs: random weighted difficulty.
    while len(songs) < count:
        name = _make_name(rng, used_names)
        used_names.add(name)
        songs.append({
            "name": name,
            "type": rng.choice(TYPES),
            "level": _weighted_pick(DIFFICULTY_POOL, rng),
        })

    return songs


def _tiers_covered(songs: list[dict]) -> bool:
    """Check that all 8 diff-score tiers are present."""
    scores = {parse_song_library({"songs": songs})[i].diff_score for i in range(len(songs))}
    return scores == {2, 3, 4, 5, 6, 8, 10, 15}


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
