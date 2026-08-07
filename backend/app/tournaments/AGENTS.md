# tournaments/ — 两赛制引擎（纯逻辑，无 DB/IO）

## OVERVIEW
`base.py` 定义 `TournamentEngine` ABC 与数据类；`swiss.py` / `single_elim.py` 实现两种赛制（round_robin 已删除，issue 7）。纯逻辑，不碰 DB/IO，由 `services/match_service` 通过 `competition.tournament_format` 字符串实例化（`points_service` 复用）。

## ENGINES
| 引擎 | 算法 | 决胜规则 |
|------|------|----------|
| `SwissEngine` | 逐轮配对（构造时仅物化第 1 轮，之后按当前 standings 经 `generate_next_round()` 逐轮生成），默认轮数 `ceil(log2 n)+1`（issue 7 用户确认，随参赛人数动态调整，无 7 轮上限），奇数场轮空给最后未轮空者，贪心+回溯完美匹配防重复对手 | points desc → Buchholz desc → net desc → seed asc |
| `SingleElimEngine` | 标准单败淘汰 bracket，规模为 ≥n 的 2 次幂，缺位成轮空；可配 `seeded`（镜像法）/ `third_place`（默认 True） | 冠军 → 亚军 → 季军赛结果 → 淘汰轮次 desc → seed asc |

## INTERFACE
- `TournamentEngine(participants: list[int], config: dict)`：`generate_schedule()` / `generate_next_round()`（swiss 特有）/ `record_result(match_id, result)` / `standings()` / `is_complete()` / `next_round()`。输入顺序即 seed 顺序（seed = index+1）。
- `MatchPlan`：`participant_b is None` + `is_bye=True` 标记轮空，轮空受益者为 `participant_a`。
- `MatchResult`：`winner` / `is_draw` / `score_a` / `score_b`。`winner is None` + `is_draw=True` = 平局（双方各 0.5 分）；否则 `winner` 必须是本局参赛者之一。`score_a/b` 喂净胜分决胜。
- `StandingRow`（issue 9/11：胜/负/平 分别展示）：`participant_id` / `wins`（整数胜场，轮空 1.0，平局不计入）/ `net_score` / `opponent_wins`（swiss 存 Buchholz；single_elim 恒 0）/ `seed` / `losses`（败场）/ `draws`（平局）/ `points`（排序用：swiss=wins+0.5·draws，single_elim=wins）。
- `RoundPlan`：全局轮号 + 该轮对局。

## VALIDATION
- 所有引擎构造时校验：participants 非 int 列表、少于 2 人、重复 → 抛 `ValueError`。
- `record_result` 通用校验（base）：match_id 不存在 / 轮空不可记分 / 重复记录 / 非平局 winner 非本局参赛者 / 平局 winner 非 None → `ValueError`。
- `SingleElimEngine.record_result` 对 draw 抛 `ValueError("单败淘汰不允许平局")`（Metis E1）。
- 错误消息**混合风格**：通用校验为英文（如 `"at least 2 participants are required"`、`"unknown match_id: {id}"`），单败淘汰禁平局为中文。改动时保持各自风格。

## TRAPS
- 后续轮次参赛者由 `_resolve_participants(match_id)` 从已记录结果解析（轮空自动晋级）；feeder 无结果时抛 `ValueError`。`services/match_service.start_match` 靠它解析单败淘汰后续轮次。
- `SingleElimEngine.is_complete()` 只看决赛是否有结果，季军赛不阻塞完成。
- 轮空自动计分（swiss 1 胜 1 分 0 净分），不可记分；`standings` 里未完成真实对局不贡献。
- swiss 赛程逐轮增量物化（base 契约中 Swiss 是例外）；`_perfect_match` 递归深度受 ≤50 人池约束。
- swiss 平局：`wins` 不计入胜场，`draws` 计数 +1、`points` +0.5 —— 排序按 `points` 而非 `wins`，改排序链时勿混用。
