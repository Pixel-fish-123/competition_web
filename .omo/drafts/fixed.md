---
slug: fixed
status: reviewed
intent: clear
review_required: true
plan_path: .omo/plans/fixed.md
plan_sha256: null
review_round_id: round-1
pending-action: handoff (awaiting user start-work)
approval: "用户 2026-08-03 批准写出完整计划（F=全部 A-E）"
review_result: "momus + Oracle 双评审完成，均 NEEDS-REVISION，6 项 blocking 已全部修订：①todo 2 ⑤ end_session 状态陈旧（路由层捕获活控制器注入 final_state）②todo 2 WS 重连守卫（1008 停止 + unmount 标记）③todo 1 drop_all 顺序（锁检测前置 + 全模型 import）④todo 7 级联补全（Match.referee_id/Competition.created_by/create_session 校验）⑤todo 8/9 显式列出需改写既有测试 ⑥todo 13 验收 grep 限定 + 第 5 处 as any"
scope_decision: "用户 2026-08-03 确认 F=全部（A-E）：对局链路阻塞 bug 修复 + 安全权限加固 + 业务逻辑调整 + 前端体验优化 + 部署工具补全，整合为一个完整计划"
confirmed_forks: "①A 积分改手动（fixed draft 已确认）②A 硬删除账号（fixed draft 已确认）③B 三赛制赛程图（fixed draft 已确认）④A 裁判 per-competition 校验（fixed draft 已确认）"
review:
  momus:
    status: pending
    workspace_root: null
    runtime_home: null
    target: .omo/plans/fixed.md
    round_id: null
    plan_sha256: null
    launch_id: null
    session: null
    result: null
  independent:
    status: pending
    workspace_root: null
    runtime_home: null
    target: .omo/plans/fixed.md
    round_id: null
    plan_sha256: null
    launch_id: null
    session: null
    result: null
approach: "用户确认 F=全部（A-E）。整合 fixed.md draft（9 todo）+ fixes plan 阻塞性 bug 细节 + 部署补全 + as any 清理 = 约 15 个 todo：①reset_db.py 重置脚本（E工具）②对局链路连环 bug 修复（A：前端解包嵌套响应+participant_id 推导+WS state 解包 controller_state+session_ended 保留状态+后端 start_match 回写参赛者+end_session 广播附 state）③前端插件化 MatchPlay（A/D：按 gameplay_plugin 名动态解析组件，映射表）④后端字段补齐（A：start_match 回写解析参赛者到 Match 行+MatchOut 补 gameplay_plugin 字段）⑤静态托管目录对齐（E：main.py frontend-dist → frontend/dist）⑥内存 _sessions 注释收敛 + admin 玩法插件列表接口 GET /api/admin/plugins（D/E）⑦权限模型补全（B：admin 增 POST 创建/DELETE 硬删账号级联清理 + 玩法路由 submit_action/end_session 补 per-competition referee_ids 校验堵越权）⑧允许删除 finished 比赛 + 级联清理 Match/GameSession/PointTransaction（C）⑨积分合并：移除 finished 自动结算 + 单一积分 admin 手动发放 + 排行榜合并（C，用户已确认 ①A）⑩首页改版：移除比赛卡片纯宣传 + 比赛列表迁移到 Competitions.vue（D）⑪比赛详情竞态修复：补 watch(route.params.cid) + loading 初值（D）⑫赛程图可视化：单败淘汰 bracket 签表 + 循环/瑞士轮次对阵表（D，用户已确认 ③B）⑬清理 4 处 as any（D：Home/CompetitionDetail/admin Competitions/Traffic）⑭部署补全（E：Dockerfile+docker-compose+Caddyfile+backup.sh+backup_restore_test.sh+部署手册+玩法模板开发规范）⑮全量回归验证（后端 pytest 全绿+前端 build+对局链路 UI 冒烟+权限/积分/删除冒烟）。工作量 XL，风险 Medium。"
---

# Draft: fixed

## Components (topology ledger)
| id | outcome | status | evidence |
|----|---------|--------|----------|
| C1 | reset_db.py：删库→重建→seed，一键重置（用户测试） | active | backend/seed.py:80,233; backend/app/db.py:10; backend/app/config.py:6-7 |
| C2 | 玩法插件对局链路打通：前端解包+participant_id+WS state+会话结束；后端回写+广播 | active | frontend/src/views/MatchPlay.vue:174-207,145-172; backend/app/plugins/triangle_occupy/plugin.py:185-196,198-281; backend/app/api/matches.py:131-155; backend/app/services/match_service.py:206-216,222-226; backend/app/plugins/routes.py:199-225 |
| C3 | 权限模型：admin 增删账号（硬删）+ referee per-competition 强制校验 | active | backend/app/api/admin_users.py:28-86（仅 PATCH 无 POST/DELETE）; backend/app/core/rbac.py:48-64; backend/app/services/match_service.py:109（_require_assigned_referee） |
| C4 | 允许删除 finished 比赛 + 级联清理 | active | backend/app/api/competitions.py:181-198（DELETABLE_STATUSES=draft/cancelled）; backend/app/models/match.py:39-80; backend/app/models/point.py:32 |
| C5 | 积分合并：移除自动结算，单一"积分"admin 发放 | active | backend/app/services/points_service.py:64-176（settle_competition_points）; backend/app/api/competitions.py:157-173（finished 自动结算）; backend/app/models/point.py:32; frontend/src/views/admin/Points.vue:26-31,52-54; frontend/src/views/Rankings.vue |
| C6 | 首页改版：移除比赛卡片，纯宣传页 + 比赛列表页 | active | frontend/src/views/Home.vue:77-198（slides+cards）; frontend/src/views/Competitions.vue（空壳） |
| C7 | 比赛详情竞态修复 | active | frontend/src/views/CompetitionDetail.vue:1-4,368-378,477-484 |
| C8 | 赛程图：单败淘汰签表 + 循环/瑞士轮次对阵 | active | frontend/src/views/CompetitionDetail.vue:132-161（现有赛程卡片）; backend/app/api/matches.py:112-128（GET matches） |
| C9 | 全量回归 | active | backend/tests/AGENTS.md; frontend/AGENTS.md |

## Open assumptions (announced defaults)
| assumption | adopted default | rationale | reversible? |
|------------|-----------------|-----------|-------------|
| 积分：移除自动结算 | 完全移除 settle_competition_points 自动调用；比赛结束不再自动发积分，全部由 admin 在后台手动发放（含比赛名次） | 用户确认 ①A | 是（保留函数但不再自动调用） |
| 账号删除方式 | 硬删除：DELETE /api/admin/users/{id} 级联清理报名/积分/队伍成员/审计引用 | 用户确认 ②A | 否（破坏性，需确认弹窗） |
| 赛程图范围 | 三种赛制：单败淘汰=签表 bracket，循环赛/瑞士轮=轮次对阵表 | 用户确认 ③B | 是 |
| 裁判权限 | 保留全局 referee 角色 + 所有裁判端点强制 per-competition referee_ids 校验（补全 match_service/plugins 之外遗漏处） | 用户确认 ④A | 是 |
| 比赛详情竞态根因 | 组件复用（路由参数变化不重新挂载）+ loading 时序：修复 = 路由 watch 重新加载 + loading 初值 true | 最可能根因；执行时验证 | 是 |
| 删除 finished 比赛 | 允许，但需级联清理 Match/GameSession/Registration/PointTransaction | 用户问题 2 | 是 |
| 重置脚本 | 完全重置无备份，CLI 带确认/--yes，PermissionError 捕获 | 沿用 competition-web-fixes 结论 | 是 |
| 积分流水 kind 字段 | 保留 DB 列（兼容历史数据）但新流水统一 kind="manual"；前端/API 不再区分类型，排行榜只显示 total | 避免数据迁移风险 | 是 |

## Findings (cited - path:lines)
1. **问题 1 权限**：admin_users.py 仅 GET list + PATCH role/status/password（:28-86），**无 POST 创建、无 DELETE 删除**；rbac.py:63-64 require_referee=admin+referee（全局角色）；match_service.py:109 `_require_assigned_referee` 已实现 per-competition referee_ids 校验（start/result 用）；但**玩法插件路由 routes.py:171 只做 require_referee，未校验裁判是否属于该比赛**——全局 referee 可操作任意比赛的玩法会话（越权风险）。
2. **问题 2 删除**：competitions.py:46 `DELETABLE_STATUSES=("draft","cancelled")`，:181-198 delete 只清 Registration，**不清理 Match/GameSession/PointTransaction**（SQLite FK 仅 metadata，无级联）。
3. **问题 3 竞态**：CompetitionDetail.vue:368-378 loadCompetition 在 onMounted 调用（:477-484），若路由参数变化（/competitions/1 → /2）组件复用不重新加载；loading 初值未确认；:3 el-empty 显示"比赛不存在"。
4. **问题 4 首页**：Home.vue:186-198 loadCompetitions 拉列表渲染卡片（:74 前模板区）；Competitions.vue 是空壳（仅标题）。
5. **问题 5 赛程图**：CompetitionDetail.vue:132-161 现有赛程卡片（el-card 列表）；GET /api/competitions/{cid}/matches 返回 MatchOut 列表（含 participant_a/b、status）；**无任何可视化组件**。
6. **问题 6 积分**：points_service.py:64-176 settle_competition_points 在 competitions.py:157-173 finished 流转时自动调用；PointTransaction.kind ∈ {competition, activity, manual}；Points.vue:26-31 发放类型下拉（activity/manual）+ :52-54 排行榜分 competition_sum/activity_sum 两列；Rankings.vue 三 tab。
7. **问题 7 插件 debug（沿用上轮评审结论）**：①MatchPlay.vue:177 `match.value=data`（嵌套 MatchDetailOut 未解包）→ participant_a/status 全 undefined；②:200 participant_id:0 硬编码；③plugin.py:185-196 get_state 嵌套 controller_state vs TriangleState 扁平接口 → 棋盘空白；④MatchPlay.vue:156-160 session_ended 清空 state → 记录结果按钮消失；⑤match_service.py:206-216 单败淘汰后续轮次解析参赛者未回写 Match 行；⑥routes.py:221-224 session_ended 广播不带 state。
8. **问题 8 重置脚本**：同 competition-web-fixes todo 1 结论（config.py:6-7 相对路径、db.py:10 WAL、seed.py:80 幂等、conftest.py:22-28 drop_all+create_all 标准做法、Windows PermissionError 捕获）。

## Decisions (with rationale)
1. **重置脚本 backend/reset_db.py**：drop_all→dispose→删文件（PermissionError 捕获）→create_all→seed_all；CLI `python reset_db.py [--yes]`。
2. **玩法插件修复 = 前端解包 + 后端回写/广播**（六处，见 findings 7）：保持插件契约不变（get_state 嵌套），前端解包 controller_state；match_service 回写解析参赛者；end_session 广播附 state。
3. **权限模型**：admin 增加 POST /api/admin/users（创建账号，含 role 指定）与 DELETE /api/admin/users/{id}（硬删除，级联清理 Registration/PointTransaction/TeamMember/Team/审计 user_id 置空或删行）；referee 全局角色保留，但**所有玩法/对局裁判端点强制校验 referee 属于该比赛 referee_ids**（routes.py 补比赛级校验，方法：根据 session→match→competition 查 referee_ids）。
4. **删除 finished 比赛**：DELETABLE_STATUSES += "finished"；级联删除 Registration→Match→GameSession→PointTransaction（按 competition_id）。
5. **积分合并**：competitions.py finished 流转移除 settle_competition_points 调用；points_service.settle_competition_points 保留函数（兼容旧测试）但不再自动触发；admin Points.vue 移除类型下拉（统一"积分"）；leaderboard API 合并为单列 total；Rankings.vue 改为单一"积分"排行榜；新流水 kind 统一 "manual"。
6. **首页改版**：Home.vue 移除比赛卡片区（保留宣传轮播+CTA），比赛列表迁移到独立路由 /competitions（Competitions.vue 实现为列表页，导航入口保留）。
7. **竞态修复**：CompetitionDetail.vue 加 `watch(() => route.params.cid, ...)` 重新加载；loading 初值 true；404 时区分"加载中/不存在"状态。
8. **赛程图**：新增前端组件 frontend/src/plugins/schedule/（或 components/）：单败淘汰签表（bracket 树状图）、循环/瑞士轮次对阵表；数据源 GET /api/competitions/{cid}/matches；集成进 CompetitionDetail.vue。
9. **回归**：全量 pytest + 前端 build + 对局链路 UI 冒烟 + 权限/积分/删除冒烟。

## Scope IN
- backend/reset_db.py 可复用重置脚本（完全重置无备份）
- 玩法插件对局链路六处修复（debug 问题 7）
- 权限模型：admin 增删账号（硬删）+ 所有裁判端点 per-competition 校验（问题 1）
- 允许删除 finished 比赛 + 级联清理（问题 2）
- 积分合并：移除自动结算 + 单一积分 admin 发放 + 排行榜合并（问题 6）
- 首页改版：移除卡片纯宣传 + 比赛列表页（问题 4）
- 比赛详情竞态修复（问题 3）
- 赛程图：单败淘汰签表 + 循环/瑞士轮次对阵（问题 5）
- 每项补回归测试 + 全量回归（问题 8 执行验证）

## Scope OUT (Must NOT have)
- 不做新玩法插件（只修现有 triangle_occupy 链路）
- 不改 demo GameController 规则逻辑
- 不改变 GameplayPlugin 契约签名与 get_state 返回形状（前端解包）
- 不引入动态 import() 做前端插件化（单玩法映射表足够）
- 不做积分历史数据迁移（保留 kind 列，新流水统一 manual）
- 不做账号删除的软删除/回收站（用户确认硬删除）
- 不重构赛制引擎算法本身（只加赛程图可视化）
- 不做 CI/CD
- 不做前端单元测试框架（沿用 npm run build）
- 不做多语言/国际化（赛程图 UI 中文）

## Open questions
无（用户已确认 4 个关键分叉：①A ②A ③B ④A）。

## Approval gate
status: awaiting-approval
approach: 见上方 approach 字段。
next-action: 用户批准后，运行 scaffold 脚本（无 --draft-only）生成 .omo/plans/fixed.md，APPEND 9 个实现 todo + F1-F4 最终验证波，再运行 momus + Oracle 高精度评审。
