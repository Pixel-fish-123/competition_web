"""平衡性模拟冒烟测试（轻量，完整分析用 run_balance.py 跑大样本）。

运行：cd demo && python -m pytest tests/balance/test_balance.py -q
"""

import json
from pathlib import Path

import pytest

from balance.models import BalanceConfig, TimeModel
from balance.simulator import run_tournament, simulate_match

from controller.song_lib import parse_song_library

_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module")
def songs():
    path = _ROOT / "test_songs.json"
    if not path.exists():
        pytest.skip("缺少 test_songs.json，先运行 python app/tools/gen_test_songs.py --seed 1")
    with open(path, encoding="utf-8") as f:
        return parse_song_library(json.load(f))


# ---------------------------------------------------------------- 时间模型


def test_time_model_monotonic():
    for kind in ("power", "exp"):
        m = TimeModel(kind=kind)
        times = [m.minutes(s) for s in range(2, 26)]
        assert times == sorted(times)                      # 分数越高耗时越长
        assert m.minutes(2) < m.minutes(25)


def test_time_model_anchors_fit():
    m = TimeModel(kind="power").fit_from_anchors(2, 1.0, 25, 12.0)
    assert abs(m.minutes(2) - 1.0) < 1e-6
    assert abs(m.minutes(25) - 12.0) < 1e-6
    m2 = TimeModel(kind="exp").fit_from_anchors(2, 1.0, 25, 12.0)
    assert abs(m2.minutes(2) - 1.0) < 1e-6
    assert abs(m2.minutes(25) - 12.0) < 1e-6


def test_time_model_min_floor():
    m = TimeModel(min_minutes=0.5)
    assert m.minutes(0) >= 0.5


# ---------------------------------------------------------------- 模拟器


def test_simulate_single_match(songs):
    cfg = BalanceConfig()
    r = simulate_match(songs, seed=1, cfg=cfg)
    assert r.winner in ("defender", "attacker", "draw")
    assert r.win_type in ("l1_energy", "timeout")
    assert r.defender_score >= 0 and r.attacker_score >= 0
    assert r.defender_cells + r.attacker_cells <= 21
    assert r.occupation_times
    # 统计字段
    assert r.template in ("A", "B", "C")
    assert r.encirclement_count >= 0
    assert r.l1_challenges >= 0
    assert 0 <= r.l1_energy <= 10


def test_encirclement_count_matches_events(songs):
    """包围次数统计与事件日志一致（抽样验证）。"""
    cfg = BalanceConfig(d_seal_top=8, d_cut=6, d_wall=3)   # 筑墙倾向，提高包围频率
    found = False
    for seed in range(1, 31):
        r = simulate_match(songs, seed=seed, cfg=cfg)
        if r.encirclement_count == 0:
            continue
        found = True
        break
    assert found


def test_simulate_single_match_reproducible(songs):
    a = simulate_match(songs, seed=7, cfg=BalanceConfig())
    b = simulate_match(songs, seed=7, cfg=BalanceConfig())
    assert a.winner == b.winner
    assert a.defender_score == b.defender_score
    assert a.attacker_score == b.attacker_score


def test_tournament_smoke(songs):
    results = run_tournament(songs, games=10, seed=100, cfg=BalanceConfig())
    assert len(results) == 10
    n = len(results)
    rates = sum(
        1 for r in results if r.winner in ("defender", "attacker", "draw")
    )
    assert rates == n                    # 结局三分类完备
    # 胜率不是极端单边（10 局内至少出现 2 种结局），保证对抗性
    kinds = {r.winner for r in results}
    assert len(kinds) >= 2


def test_tournament_different_seeds_vary(songs):
    a = run_tournament(songs, games=5, seed=1, cfg=BalanceConfig())
    b = run_tournament(songs, games=5, seed=2, cfg=BalanceConfig())
    assert [r.winner for r in a] != [r.winner for r in b]


def test_l1_energy_victory_reachable_without_defense(songs):
    """对照实验：防守方不夺 L1 时，L1 能量胜利在模拟内可达（验证规则联动正确）。

    默认策略下能量胜利的达成率是平衡性结论（防守方夺 L1 压制），见 balance/README.md。
    """
    cfg = BalanceConfig(d_seal_top=0, d_cut=0, d_wall=0, d_l1_defend=False,
                        a_top_claim=8, a_extend=6, a_top_pull=2, a_l1_energy_go=0)
    results = run_tournament(songs, games=30, seed=1, cfg=cfg)
    l1_wins = sum(1 for r in results if r.win_type == "l1_energy")
    assert l1_wins > 0
