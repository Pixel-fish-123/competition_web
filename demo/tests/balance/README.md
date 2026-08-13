# 平衡性对战模拟（tests/balance/）

> 用途：对「三角占领」玩法做**平衡性调整**的量化工具——估算不同分数格子的挑战时间，
> 统计既定规则与策略下双方的胜率，为后续规则调整提供基线。

## 模型

**占领时间模型**（`models.py`）：分数越高的格子挑战耗时越长，等效拟合为

- 幂函数：`t(s) = a * s ** b`（默认 `a=0.365, b=1.133`，锚点 t(2)≈0.8min、t(25)≈14min）
- 指数函数：`t(s) = a * exp(b * s)`（`--time-model exp` 切换）

参数可用 `--model-a/--model-b` 直接覆盖，或用 `fit_from_anchors(s1,t1,s2,t2)` 按实测数据重标定。

**对战模拟器**（`simulator.py`）：蒙特卡洛。在真实棋盘上复用 `controller.game.GameController`
的完整规则（激活 / 新包围 / 计分 / 顶端直胜 / 更新链），把「占领」包装为耗时任务：
每方最多并行 `team_size` 人（默认 3），任务耗时 = 时间模型(格子总分)；时间推进到任务完成事件
再执行真实占领；25 分钟限时或顶端直胜结束一局。双方用启发式评分选目标（权重见 `BalanceConfig`，
含封顶 / 切断 / 筑墙 / 能源接入 / 路径扩展 / 冲顶牵引，外加噪声），产生有代表性的攻防对抗。

## 运行

```bash
cd demo
python tests/balance/run_balance.py                      # 默认 200 局 → 报告
python tests/balance/run_balance.py --games 500 --seed 42 --time-model exp
python tests/balance/run_balance.py --model-a 0.3 --model-b 1.2 --out report.md
```

报告输出：`tests/balance/output/balance_report.md`，包含

1. 分数 → 挑战时间表（理论模型 + 模拟观测对比）
2. 双方胜率（防守胜 / 攻击胜 / 平局 / 顶端直胜占比）
3. 平均比分、平均占领格数、L1 终局持有分布
4. 模拟配置回显

## 冒烟测试

```bash
cd demo && python -m pytest tests/balance/test_balance.py -q
```

## 平衡性调整指引

- 想削弱防守方：调低 `d_seal_top` / `d_cut` / `d_wall`，或调高 `a_extend` / `a_top_pull`；
- 想削弱攻击方：调低 `a_energy_base` / `a_top_pull`，或调高 `d_*` 系列；
- 想改变节奏：改时间模型参数（低分格更快 / 高分格更慢）与 `team_size` / `time_limit_minutes`；
- 全部参数集中在 `BalanceConfig`（models.py），改完重跑报告对比胜率即可。

## 基线发现（2026-08 默认配置，200 局）

- 占领时间：低分格（2~4 分）约 **1.6min**，中分格（7~9 分）约 **3.9min**，
  高分格（13~15 分）约 **7.1min**，顶分格（20~25 分）约 **11.3min**（模拟观测与幂模型吻合）；
- 胜率：防守方 **53.5%** : 攻击方 **45.5%**（计时比分），平局 1%；平均比分 87 : 109（攻击方格均分更高）；
- **顶端直胜 0/200**：当前规则下冲顶极难达成——防守方「封顶（占 L2）+ 切断路径 + 夺回 L1」
  三重防御使攻击方几乎无法同时满足「持有 L1 且 L2 激活」；
  对照实验（防守方放弃封顶/切断）直胜约 10%，证明机制本身可达，被策略压制是平衡性结论。
- 若后续调整方向是「让直胜更有存在感」，建议优先削弱防守方夺 L1 / 封顶权重，或给攻击方
  路径格更低耗时。
