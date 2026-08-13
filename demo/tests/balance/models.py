"""占领时间模型：分数越高的格子占领耗时越长，等效拟合成幂函数或指数函数。

用于平衡性对战模拟：给定格子总分 total_score（diff_score + task_bonus），
估算单格挑战耗时（分钟）。模型参数可配置，便于用实测数据重新标定。

- 幂函数：  t(s) = a * s ** b
- 指数函数：t(s) = a * exp(b * s)

默认锚点标定（幂模型 a=0.365, b=1.133）：t(2)≈0.8min、t(25)≈14min，
即低分格约 1 分钟、满分格约 14 分钟（25 分钟限时内单方 3 人并行约可完成 6~10 格）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# 常见分值档位（歌曲分 × 任务分组合，10 分制总分 2~20），用于报告展示
REFERENCE_SCORES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20]


@dataclass
class TimeModel:
    kind: str = "power"          # "power" | "exp"
    a: float = 0.0803            # 幂/指数模型的系数（新总分域 2~20 标定）
    b: float = 1.674             # 幂/指数模型的指数
    min_minutes: float = 0.5     # 耗时下限（分钟），防止极端低分格耗时趋近 0

    def minutes(self, total_score: int | float) -> float:
        s = max(float(total_score), 0.0)
        if self.kind == "exp":
            t = self.a * math.exp(self.b * s)
        else:  # power
            t = self.a * (s ** self.b)
        return max(t, self.min_minutes)

    def fit_from_anchors(self, s1: float, t1: float, s2: float, t2: float,
                         kind: str | None = None) -> "TimeModel":
        """用两个锚点 (s1,t1) (s2,t2) 重新标定参数（s1 < s2, t1 < t2）。"""
        if kind is not None:
            self.kind = kind
        if self.kind == "exp":
            self.b = math.log(t2 / t1) / (s2 - s1)
            self.a = t1 / math.exp(self.b * s1)
        else:
            self.b = math.log(t2 / t1) / math.log(s2 / s1)
            self.a = t1 / (s1 ** self.b)
        return self

    def table(self, scores: list[int] | None = None) -> list[tuple[int, float]]:
        """返回 (总分, 分钟) 表，用于报告展示。"""
        out = []
        for s in (scores or REFERENCE_SCORES):
            out.append((s, round(self.minutes(s), 2)))
        return out

    def describe(self) -> str:
        if self.kind == "exp":
            return f"指数函数  t(s) = {self.a:.4f} * e^({self.b:.4f} * s)"
        return f"幂函数    t(s) = {self.a:.4f} * s^{self.b:.4f}"


@dataclass
class BalanceConfig:
    """对战模拟的可配置参数（平衡性调整的旋钮）。"""

    time_limit_minutes: float = 25.0
    team_size: int = 3                    # 每方同时进行中的挑战数（3 人团队）
    time_model: TimeModel = field(default_factory=TimeModel)
    l1_challenge_minutes: float = 2.0     # L1 挑战耗时（分钟；=完整打一首歌的成本，对照实验 B 为均衡点）
    l1_energy_target: int = 10            # L1 能量胜利目标点数（用户最终确认值 10）
    l1_energy_interval: float = 2.0       # 攻击方持有 L1 期间积累间隔（分钟，调大 -> 攻击方更难）
    l1_score_lo: int = 950000             # L1 挑战分数区间
    l1_score_hi: int = 1000000
    l1_tp_lo: float = 98.0
    l1_tp_hi: float = 100.0

    # 策略权重（越高越重视该目标）
    d_ratio: float = 1.0                  # 防守方：性价比（总分/耗时）
    d_seal_top: float = 3.0               # 防守方：封顶（占 L2 阻止冲顶）
    d_cut: float = 3.0                    # 防守方：切断（占攻击方激活块邻接的空格）
    d_wall: float = 0.5                   # 防守方：邻接己方格越多的格越优先（筑墙）
    d_l1_defend: bool = True              # 防守方：攻击方持有 L1 时立即夺回（防能量积累）
    a_ratio: float = 0.6                  # 攻击方：性价比（低分快占，铺路径）
    a_energy_base: float = 8.0            # 攻击方：L6 能源接入格
    a_extend: float = 4.0                 # 攻击方：邻接己方激活块的扩展格
    a_top_pull: float = 1.2               # 攻击方：向 L1（浅层）方向牵引
    a_top_claim: float = 5.0              # 攻击方：抢占 L2（冲顶关键格）
    a_l1_energy_go: int = 0               # 攻击方：L1 能量达到该值后全力夺 L1（0=开局即抢，能量胜利冲刺）
    noise: float = 0.4                    # 策略评分噪声（越大越随机）

    def describe(self) -> str:
        return (
            f"限时 {self.time_limit_minutes}min / 每方并行 {self.team_size} 人 / "
            f"L1 挑战 {self.l1_challenge_minutes}min / 噪声 {self.noise}\n"
            f"  防守方权重: 性价比={self.d_ratio} 封顶={self.d_seal_top} "
            f"切断={self.d_cut} 筑墙={self.d_wall} 夺L1={self.d_l1_defend}\n"
            f"  攻击方权重: 性价比={self.a_ratio} 能源接入={self.a_energy_base} "
            f"扩展={self.a_extend} 冲顶牵引={self.a_top_pull} 抢L2={self.a_top_claim} "
            f"L1冲刺={self.a_l1_energy_go}"
        )
