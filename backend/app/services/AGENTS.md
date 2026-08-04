# services/ — 业务编排层（对局生命周期 + 积分结算）

## OVERVIEW
`match_service.py`（排表/开赛/记分）+ `points_service.py`（积分幂等结算/排行榜），编排 `tournaments/` 纯逻辑引擎，是 api 层与引擎之间的唯一业务入口。玩法插件已从对局流程解耦（对局由裁判手工管理，demo 玩法日志经 gameplay-log 端点导入展示，不参与赛程）。

## FLOW
```
build_schedule_for_competition（比赛进 ongoing 时）
  → _approved_participant_ids（只认 status=="approved"，participant id 升序）
  → _build_engine（按 tournament_format 实例化）
  → engine.generate_schedule() → 落 Match 行（engine_match_id 写入）
  → 轮空对局直接 finished / result_type=win（winner=participant_a）

start_match（裁判开赛）
  → _require_assigned_referee（referee.id 必须在 competition.referee_ids，否则 403）
  → 轮空对局幂等完结返回 finished
  → 单败淘汰后续轮次参赛者未知：_rebuild_engine + _replay_finished → engine._resolve_participants
  → match.status=in_progress → manager.broadcast {"type": "match_started", "match_id"}
  （不创建 GameSession / 不调用插件）

record_match_result（裁判记分）
  → 单败淘汰禁平局（Metis E1，payload.is_draw 直接 400）
  → _rebuild_engine + _replay_finished → engine.record_result → 落库 finished
  → manager.broadcast {"type": "score_update", ...}
```

## KEY FUNCTIONS
| 函数 | 文件 | 作用 |
|------|------|------|
| `build_schedule_for_competition` | match_service | 不足 2 名 approved 返回空赛程；轮空直接 finished 记 win |
| `start_match` | match_service | 校验裁判归属 → in_progress → 广播 match_started（不建玩法会话） |
| `record_match_result` | match_service | 单败淘汰禁平局 → 引擎 record_result → 落库 + 广播 score_update |
| `_approved_participant_ids` | match_service | 已批准报名 id 升序（确定性 seed 顺序） |
| `_build_engine` | match_service | 按 tournament_format 实例化引擎；格式非法抛 ValueError |
| `_rebuild_engine` / `_replay_finished` | match_service | 重建引擎 + 按 Match.id 升序回放已完结对局 |
| `settle_competition_points` | points_service | 幂等结算（已存在 competition 流水则返回 []）；队伍成员各得全额 |
| `get_competition_standings` | points_service | 重建引擎 + 回放 → engine.standings()（best-first） |
| `get_leaderboard` / `get_user_points` | points_service | 全局榜聚合 / 用户余额 |

## TRAPS
- **points_service import match_service 的私有 `_` 助手**（`_approved_participant_ids` / `_build_engine` / `_replay_finished`）：改名或重构须同步两边，否则积分结算与对局引擎重建逻辑漂移。
- `_replay_finished` 按 `Match.id` 升序回放 = 按 schedule 顺序回放（排表时 Match 行按 schedule 迭代顺序创建），前序轮次必先于后续轮次进入引擎；轮空对局跳过（引擎按 is_bye 自动计分）。
- `_replay_finished` 对 ValueError 静默 continue（数据不一致不应发生，跳过避免阻塞其它对局）。
- `start_match` 不再创建玩法会话/调用插件；对局结果一律由裁判手工输入。
- `settle_competition_points` 存在未完成对局时 raise ValueError("存在未完成的对局，无法结算")；少于 2 名参赛者返回 []。
- 积分规则 `points_rule` 为 {名次str→积分} dict，无该名次取 `default`，再无则 0（不产生流水）。
- `match.gameplay_log`（api/matches.py 导入端点写入）仅供展示，不参与引擎重建/回放。
