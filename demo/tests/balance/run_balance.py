"""平衡性对战模拟入口：输出「分数→挑战时间」表与「双方胜率」报告。

用法（在 demo/ 目录下）：
    python tests/balance/run_balance.py                    # 默认 200 局
    python tests/balance/run_balance.py --games 500 --seed 42
    python tests/balance/run_balance.py --time-model exp
    python tests/balance/run_balance.py --model-a 0.3 --model-b 1.2 --out report.md

报告输出：tests/balance/output/balance_report.md（--out 可改路径）。
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

# 定位 demo 根目录（本脚本位于 demo/tests/balance/ 下）
_BALANCE_DIR = Path(__file__).resolve().parent
_TESTS_DIR = _BALANCE_DIR.parent
_ROOT = _TESTS_DIR.parent
_APP_DIR = _ROOT / "app"
for _p in (str(_APP_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:                                   # pytest 包模式
    from .models import BalanceConfig, TimeModel
    from .simulator import run_tournament
except ImportError:                    # 直接脚本模式
    from models import BalanceConfig, TimeModel
    from simulator import run_tournament

from controller.song_lib import parse_song_library  # noqa: E402

SCORE_BUCKETS = [(2, 4), (5, 6), (7, 9), (10, 12), (13, 15), (16, 19), (20, 25)]


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """二项比例 Wilson 95% 置信区间（k 成功 / n 样本）。"""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _fmt_rate(k: int, n: int) -> str:
    """如 53.5% (46.4~60.4)。"""
    lo, hi = _wilson_ci(k, n)
    return f"{k / n * 100:.1f}% ({lo * 100:.1f}~{hi * 100:.1f})"


def load_songs(root: Path) -> list:
    path = root / "test_songs.json"
    if not path.exists():
        sys.exit(f"[错误] 缺少歌曲库 {path}，请先运行：python app/tools/gen_test_songs.py --seed 1")
    with open(path, encoding="utf-8") as f:
        return parse_song_library(json.load(f))


def _score_bucket(total: int) -> str:
    for lo, hi in SCORE_BUCKETS:
        if lo <= total <= hi:
            return f"{lo}~{hi}"
    return str(total)


def build_report(results, cfg: BalanceConfig, games: int, seed: int) -> str:
    model = cfg.time_model
    lines: list[str] = []
    add = lines.append

    add("# 三角占领 · 平衡性对战模拟报告")
    add("")
    add(f"> 生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；"
        f"局数：{games}（种子 {seed}~{seed + games - 1}）；全部使用真实棋盘与 GameController 规则"
        f"（激活 / 新包围 / 计分 / 顶端直胜 / 更新链）")
    add("")
    add("## 1. 占领时间模型")
    add("")
    add(f"- 模型：{model.describe()}")
    add(f"- 锚点标定：t(6)≈{model.minutes(6):.1f}min、t(20)≈{model.minutes(20):.1f}min"
        f"（可用 `--model-a/--model-b` 或 fit_from_anchors 重新标定）")
    add("")
    add("### 1.1 不同分数对应的大致挑战时间（理论模型）")
    add("")
    add("| 格子总分 | 挑战时间(min) | 格子总分 | 挑战时间(min) |")
    add("|---|---|---|---|")
    table = model.table()
    half = (len(table) + 1) // 2
    for i in range(half):
        s1, t1 = table[i]
        if i + half < len(table):
            s2, t2 = table[i + half]
            add(f"| {s1} | {t1:.2f} | {s2} | {t2:.2f} |")
        else:
            add(f"| {s1} | {t1:.2f} | | |")
    add("")
    add("### 1.2 模拟观测到的实际挑战时间（按总分分桶平均）")
    add("")
    samples = [item for r in results for item in r.occupation_times]
    by_bucket: dict[str, list[float]] = {}
    for total, minutes in samples:
        if total == 0:      # L1 挑战单独统计
            continue
        by_bucket.setdefault(_score_bucket(total), []).append(minutes)
    add("| 总分区间 | 样本数 | 平均耗时(min) | 理论耗时(min) |")
    add("|---|---|---|---|")
    for lo, hi in SCORE_BUCKETS:
        key = f"{lo}~{hi}"
        bucket_samples = by_bucket.get(key, [])
        mid = (lo + hi) / 2
        if bucket_samples:
            add(f"| {key} | {len(bucket_samples)} | {statistics.mean(bucket_samples):.2f} "
                f"| {model.minutes(mid):.2f} |")
        else:
            add(f"| {key} | 0 | - | {model.minutes(mid):.2f} |")
    add("")

    add("## 2. 双方胜率（蒙特卡洛）")
    add("")
    counts = Counter(r.winner for r in results)
    n = len(results)
    l1_wins = sum(1 for r in results if r.win_type == "l1_energy")
    add("| 结局 | 局数 | 占比 |")
    add("|---|---|---|")
    for label, key in (("防守方胜（计时）", "defender"), ("攻击方胜（计时）", "attacker"),
                       ("平局", "draw")):
        add(f"| {label} | {counts.get(key, 0)} | {_fmt_rate(counts.get(key, 0), n)} |")
    add(f"| **攻击方 L1 能量胜利** | {l1_wins} | {_fmt_rate(l1_wins, n)} |")
    add("")

    add("### 2.1 模板分组胜率（A/B/C，95% 置信区间）")
    add("")
    add("| 模板 | 局数 | 防守胜 | 攻击胜 | 平局 | L1 能量胜利 |")
    add("|---|---|---|---|---|---|")
    for tmpl in ("A", "B", "C"):
        group = [r for r in results if r.template == tmpl]
        m = len(group)
        if m == 0:
            add(f"| {tmpl} | 0 | - | - | - | - |")
            continue
        d = sum(1 for r in group if r.winner == "defender")
        a = sum(1 for r in group if r.winner == "attacker")
        dr = sum(1 for r in group if r.winner == "draw")
        tp = sum(1 for r in group if r.win_type == "l1_energy")
        add(f"| {tmpl} | {m} | {_fmt_rate(d, m)} | {_fmt_rate(a, m)} | "
            f"{dr / m * 100:.1f}% | {tp / m * 100:.1f}% |")
    add("")

    add("### 2.2 包围与 L1 能量统计")
    add("")
    enc_games = sum(1 for r in results if r.encirclement_count > 0)
    enc_total = sum(r.encirclement_count for r in results)
    enc_max = max((r.encirclement_count for r in results), default=0)
    l1_games = sum(1 for r in results if r.l1_challenges > 0)
    l1_total = sum(r.l1_challenges for r in results)
    l1_energy_avg = statistics.mean(r.l1_energy for r in results)
    add(f"- **包围触发**：{enc_games} 局（{enc_games / n * 100:.1f}%）发生包围，"
        f"合计 {enc_total} 次（平均 {enc_total / n:.2f} 次/局，单局最多 {enc_max} 次）")
    add(f"- **L1 挑战**：{l1_games} 局（{l1_games / n * 100:.1f}%）发生 L1 挑战，"
        f"合计 {l1_total} 次（平均 {l1_total / n:.2f} 次/局）；平均终局 L1 能量 {l1_energy_avg:.2f}/7")
    add("")
    add("### 2.3 比分与占领统计（平均）")
    add("")
    def_score = statistics.mean(r.defender_score for r in results)
    atk_score = statistics.mean(r.attacker_score for r in results)
    def_cells = statistics.mean(r.defender_cells for r in results)
    atk_cells = statistics.mean(r.attacker_cells for r in results)
    l1_def = sum(1 for r in results if r.l1_holder == "defender")
    l1_atk = sum(1 for r in results if r.l1_holder == "attacker")
    add(f"- 平均比分：防守方 {def_score:.1f} : 攻击方 {atk_score:.1f}")
    add(f"- 平均占领格数：防守方 {def_cells:.1f} 格 : 攻击方 {atk_cells:.1f} 格")
    add(f"- L1 终局持有：防守方 {l1_def} 局 / 攻击方 {l1_atk} 局 / 未占领 {n - l1_def - l1_atk} 局")
    add("")
    add("## 3. 模拟配置")
    add("")
    add("```")
    add(cfg.describe())
    add("```")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="三角占领平衡性对战模拟")
    parser.add_argument("--games", type=int, default=200, help="模拟局数（默认 200）")
    parser.add_argument("--seed", type=int, default=1, help="随机种子（默认 1）")
    parser.add_argument("--time-model", choices=["power", "exp"], default="power",
                        help="时间模型：幂函数（默认）或指数函数")
    parser.add_argument("--model-a", type=float, default=None, help="时间模型系数 a")
    parser.add_argument("--model-b", type=float, default=None, help="时间模型指数 b")
    parser.add_argument("--out", type=str, default=None,
                        help="报告输出路径（默认 tests/balance/output/balance_report.md）")
    parser.add_argument("--quiet", action="store_true", help="只输出摘要，不打印完整报告")
    args = parser.parse_args()

    if args.games < 1:
        print("[错误] --games 必须 >= 1", file=sys.stderr)
        return 1

    model = TimeModel(kind=args.time_model)
    if args.model_a is not None:
        model.a = args.model_a
    if args.model_b is not None:
        model.b = args.model_b
    cfg = BalanceConfig(time_model=model)

    songs = load_songs(_ROOT)
    print(f"[加载] 歌曲库 {len(songs)} 首")
    print(f"[模拟] {args.games} 局，种子 {args.seed}，模型：{model.describe()}")

    results = run_tournament(songs, args.games, args.seed, cfg)

    report = build_report(results, cfg, args.games, args.seed)
    if not args.quiet:
        print("")
        print(report)

    out_path = Path(args.out) if args.out else _BALANCE_DIR / "output" / "balance_report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n[完成] 报告已写入：{out_path}")

    counts = Counter(r.winner for r in results)
    n = len(results)
    l1w = sum(1 for r in results if r.win_type == "l1_energy")
    enc = sum(1 for r in results if r.encirclement_count > 0)
    l1g = sum(1 for r in results if r.l1_challenges > 0)
    print(f"[摘要] 防守胜 {counts.get('defender', 0)} ({_fmt_rate(counts.get('defender', 0), n)}) / "
          f"攻击胜 {counts.get('attacker', 0)} ({_fmt_rate(counts.get('attacker', 0), n)}) / "
          f"平局 {counts.get('draw', 0)} / L1能量胜利 {l1w} / "
          f"包围触发 {enc} 局 / L1 挑战 {l1g} 局")
    return 0


if __name__ == "__main__":
    sys.exit(main())
