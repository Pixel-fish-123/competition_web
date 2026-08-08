# services/ — 业务编排层（对局生命周期 + 排名）

## OVERVIEW
`match_service.py`（排表/开赛/记分/瑞士轮推进）+ `points_service.py`（用户余额/全局榜/场次排名），编排 `tournaments/` 纯逻辑引擎，是 api 层与引擎之间的唯一业务入口。积分纯手动（比赛结算已整体删除，issue 6）；玩法日志仅经 gameplay-log 端点导入展示，不参与赛程。

## FLOW
```
build_schedule_for_competition（比赛进 ongoing 时）
  → _approved_participant_ids（只认 status=="approved"，participant id 升序）
  → _build_engine（按 tournament_format 实例化，swiss/single_elim）
  → engine.generate_schedule() → 落 Match 行（engine_match_id 写入）
  → 轮空对局直接 finished / result_type=win（winner=participant_a）

start_match（裁判开赛）
  → _require_assigned_referee（referee.id 必须在 competition.referee_ids，否则 403）
  → 轮空对局幂等完结返回 finished
  → 单败淘汰后续轮次参赛者未知：_rebuild_engine + _replay_finished → engine._resolve_participants
  → match.status=in_progress → manager.broadcast {"type": "match_started", "match_id"}

record_match_result（裁判记分，issue 14；按轮次锁定，用户确认）
  → 单败淘汰禁平局（Metis E1，payload.is_draw 直接 400）
  → result_locked 的对局直接 400「结果已锁定，无法更改」
  → lock=true 仅当本轮全部真实对局结束后接受，否则 400
  → _rebuild_engine + _replay_finished → engine.record_result → 落库 finished
  → 不再自动物化下一轮（下一轮由 complete_round「开始下一轮」显式生成）
  → manager.broadcast {"type": "score_update", ...}

complete_round（「开始下一轮」：锁定本轮 + 推进下一轮）
  → 仅允许结束最新一轮（防止旧轮配对基于未锁定结果）
  → lock_round（本轮全部真实对局结束才可锁）→ swiss：_advance_swiss_if_due
    → 锁定与推进同一事务提交（commit=False 参数），失败整体回滚可重试
  → 返回 (locked_count, next_round_id)；最后一轮 next_round_id=None

_advance_swiss_if_due（瑞士轮逐轮物化）
  → 仅 swiss；参赛者 < 2 直接 return
  → _rebuild_engine + _replay_finished（能看到刚提交的结果）→ 引擎逐轮
    generate_next_round → _materialize_round 幂等落库 → 单次 commit
    （complete_round 内部传 commit=False，由外层统一提交）
```

## KEY FUNCTIONS
| 函数 | 文件 | 作用 |
|------|------|------|
| `build_schedule_for_competition` | match_service | 不足 2 名 approved 返回空赛程；轮空直接 finished 记 win |
| `start_match` | match_service | 校验裁判归属 → in_progress → 广播 match_started |
| `record_match_result` | match_service | 锁定校验（lock 需本轮全部结束）→ 单败禁平局 → 引擎 record_result → 落库 + lock 标记 + 广播 |
| `lock_round` / `complete_round` | match_service | 按轮次锁定 / 「开始下一轮」（锁定+物化下一轮，单事务，仅限最新一轮） |
| `_approved_participant_ids` | match_service | 已批准报名 id 升序（确定性 seed 顺序） |
| `_build_engine` | match_service | 按 tournament_format 实例化引擎（swiss/single_elim）；格式非法抛 ValueError |
| `_rebuild_engine` / `_replay_finished` | match_service | 重建引擎 + 按 Match.id 升序回放已完结对局（abandoned/轮空行天然跳过） |
| `_advance_swiss_if_due` / `_materialize_round` | match_service | 瑞士轮逐轮物化（幂等，崩溃/竞态兜底） |
| `get_competition_standings` | points_service | 重建引擎 + 回放 → engine.standings()（best-first，含胜/负/平，issue 11） |
| `get_leaderboard` / `get_user_points` | points_service | 全局榜聚合 / 用户余额 |

## TRAPS
- **points_service import match_service 的私有 `_` 助手**（`_approved_participant_ids` / `_build_engine` / `_replay_finished`）：改名或重构须同步两边，否则场次排名与对局引擎重建逻辑漂移。
- `_replay_finished` 按 `Match.id` 升序回放 = 按 schedule 顺序回放；轮空对局跳过（引擎按 is_bye 自动计分）；`result_type="abandoned"` 或 result 缺失的对局 record_result 抛 ValueError → 静默 continue（作废对局不参与排名，issue 8）。
- `record_match_result` 允许 finished 状态重新记分（人工修改结果）；**锁定后（result_locked）任何再记分均 400**。
- `_advance_swiss_if_due` 参赛者 < 2 时直接 return（空比赛 finish 不再抛 ValueError，issue 8）。
- `settle_competition_points` 已删除（issue 6 用户确认：积分只能由 admin 手动发放，无系统结算入口）。
