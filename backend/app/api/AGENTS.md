# API 层（backend/app/api/）

## OVERVIEW
FastAPI 路由层：11 个模块，全部端点在此声明，权限/审计/限流在此落地；业务逻辑委托给 services/，本层只做参数校验、依赖注入与序列化。

## ROUTE MAP
| 模块 | 端点 | 权限 | 要点 |
|------|------|------|------|
| auth | POST /api/auth/register, /login | 公开（10/min） | 注册即自动登录；login 先查 lockout（423）再验密码；失败记 `login_failed` 审计 |
| auth | POST /api/auth/logout | 公开 | 删 cookie |
| auth | GET/PATCH /api/auth/me | get_current_user | PATCH 仅改昵称（None=不改），写 `update_profile` 审计 |
| teams | POST /api/teams | get_current_user | 建队者即队长；已入队者 400；队名唯一（IntegrityError→400） |
| teams | POST /api/teams/{id}/members | 队长 | 拉人按 user_id 优先、username 兜底；满 3 人 400 |
| teams | DELETE /api/teams/{id}/members/{uid} | 队长 | 队长不能退队（400） |
| teams | DELETE /api/teams/{id} | 队长 | 先删成员行再删队 |
| teams | GET /api/teams/my, /api/teams/{id} | get_current_user | `/my` 必须先于 `/{team_id}` 声明 |
| registrations | POST/DELETE /api/competitions/{cid}/register | get_current_user | 报名置 pending；容量按 pending+approved 计；队伍报名存队长 user_id |
| registrations | GET /api/competitions/{cid}/registrations, /api/my/registrations | get_current_user | 列表解析参赛者名称 |
| registrations | POST /api/admin/competitions/{cid}/registrations/{rid}/approve\|reject | require_admin | 仅 pending 可处理；写 `registration_approve/reject` 审计 |
| competitions | GET /api/competitions, /{id} | 公开（无鉴权） | 列表 id 降序 |
| competitions | POST/DELETE /api/competitions | require_admin | referee_ids 全量校验（须为 referee 角色）；**DELETE 任意状态可删**（issue 1，级联清理赛程/报名/积分流水） |
| competitions | POST /api/competitions/{id}/status | require_admin | 状态机 TRANSITIONS 表；进 ongoing 自动排表；finished 守卫未完成对局，`force:true` 强制结束（未完成对局置 result_type=abandoned，不参与排名，issue 8）；积分不自动结算 |
| matches | GET /api/competitions/{cid}/matches, /api/matches/{id} | get_current_user | 列表按 round_id,id 排序 |
| matches | POST /api/matches/{id}/start, /result | require_referee + 本场 referee_ids | 轮空自动完结；`result` 带 `lock:true` 保存并锁定（锁定后 400 拒绝再改，issue 14）；写 `match_start/match_result` 审计 |
| matches | POST /api/matches/{id}/randomize-sides | require_referee + 本场 referee_ids | 开赛前随机选边（issue 2）：等概率交换 participant_a/b；仅 pending 且双方已定对局；写 `match_randomize_sides` 审计 |
| matches | POST /api/bot/matches/{id}/randomize-sides | `X-Bot-Token` == 配置的 `BOT_API_TOKEN`（未配置 503） | bot `.ts start` 开局前自动随机选边；与裁判版同规则但跳过 referee_ids 校验（令牌即信任）；写 `match_randomize_sides_bot` 审计 |
| matches | POST /api/matches/{id}/gameplay-log | require_referee + 本场 referee_ids | 导入 demo 玩法日志（JSON/CSV）；?sync=true 预填 result；写 `match_gameplay_log_import` 审计 |
| announcements | GET /api/announcements(/{id}) | 公开 | 公告列表（时间倒序）/ 详情（含附件元数据） |
| announcements | GET /api/announcements/files/{stored_name} | get_current_user | 附件下载（uuid 磁盘名定位，防路径穿越） |
| announcements | POST/DELETE /api/admin/announcements | require_admin | multipart 发布（title/body/files[]，pdf/word/zip ≤50MB）；删除连磁盘文件；写审计 |
| points | GET /api/points/me, /leaderboard | get_current_user | 流水最新在前；leaderboard 按 kind 过滤 |
| points | POST /api/admin/points | require_admin | 积分唯一来源（kind=activity/manual，仅 admin 手动发放）；写 `points_grant` 审计 |
| rankings | GET /api/rankings/competition/{id}, /global | get_current_user | 场次榜=引擎 standings 重建+回放（含 wins/losses/draws/points，issue 11）；global 复用 points leaderboard |
| admin_users | GET /api/admin/users, POST, PATCH /api/admin/users/{id} | require_admin（router 级） | 创建/改角色/重置密码（**无封禁 status 选项**，issue 4）；DELETE 硬删：未完结对局判对手胜（issue 3）+ 级联清理 + 最后管理员保护 |
| admin_traffic | GET /api/admin/traffic/{summary,failed-logins,logs} | require_admin（router 级） | 数据源=AuditLog 表（锁定账号端点已删，issue 15）；logs 支持 action/username 过滤+分页 |
| ws | WS /ws/matches/{match_id} | Cookie 鉴权 + 订阅白名单 | 鉴权在此（非 ws_manager）；4401 未授权、1008 权限/频率超限 |
| health | GET /api/health | 公开 | 返回 {"status":"ok"} |

## CONVENTIONS
- 权限三档：`get_current_user`（登录即可）→ `require_referee`（=admin+referee）→ `require_admin`。裁判端点还要比赛级校验（`staff.id in competition.referee_ids`，在 match_service 内）。
- 审计：状态变更端点统一 `log_audit(db, actor_id, kind, ip, user_agent, detail)`，kind 用中文语义（`registration_approve`/`match_start`/`points_grant`/`admin_update_user`）；`_request_meta(request)` 取 (ip, user_agent)。
- 限流：`admin_*` 路由 60/min、auth 10/min（显式 `@limiter.limit`），其余走默认 100/min。
- 路径参数一律 `int` 化（`{team_id:int}` 语义）；`/api/teams/my` 必须先于 `/api/teams/{team_id}` 声明，否则 "my" 被 int 参数吞掉。
- 序列化统一走 `_xxx_out(db, obj)` 助手（`_team_out`/`_registration_out`/`_match_out`），批量 JOIN 避免 N+1。
- 公开端点（competitions 列表/详情、health）不挂鉴权依赖。

## TRAPS
- **matches.record_result 返回前必须走 `_match_out`**：直接 `return result`（ORM 对象）会漏 `participant_a_name/b_name` 字段。start/result 都返回序列化结果。
- 报名容量按 `status in ("pending","approved")` 计，重复报名检查先于容量检查（已报名者即使满员也报"已报名"而非"已满"）。
- 队伍报名在 Registration 存 `user_id=队长`，成员无独立行；`_existing_registration` 靠 user_id 匹配，队伍成员报名会被误判为"已报名"。
- 状态机 `finished` 是终态：进 finished 前守卫未完成对局（400）；`force:true` 跳过守卫，未完成对局标记为作废（`result_type="abandoned"`、result=None）—— `_replay_finished` 对无 result 的对局静默跳过，不参与排名。
- **阵营约定（用户确认）**：守护者=defender=蓝方=participant_b，掠夺者=attacker=红方=participant_a；页面统一标注「掠夺者/守护者」。gameplay-log 判定解析 demo「游戏结束 - 守护者获胜 (守85 : 掠72)」system 事件与「顶端直胜」victory 事件（详见 matches.py `_extract_scores_and_winner`）。
- gameplay-log 导入端点：`require_referee` + 比赛级 `referee_ids` 校验（admin 旁路）；`?sync=true` 预填 `match.result`（score_a=掠夺者分、score_b=守护者分），不结束对局、不触碰引擎；最终结果由裁判「保存结果」（POST /result + lock=true）落库并锁定。
- **随机选边一致性**：randomize-sides 交换 DB 行 participant_a/b，但引擎 MatchPlan 顺序排表时固定 —— 记分/回放必须经 `match_service._align_scores_to_engine` 把 score_a/b 归位到引擎坐标系，否则净胜分归属错乱（winner 是 id 无需对齐）。
- admin_users 最后管理员保护：仅当 `user.id==current_user.id` 且降级时检查 admin 总数==1；删除用户保护：不能删自己/最后一个 admin/创建过比赛的用户。
