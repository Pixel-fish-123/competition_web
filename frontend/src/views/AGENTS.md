# VIEWS KNOWLEDGE BASE

**Scope:** `frontend/src/views/`（7 个公开页面 + `admin/` 6 个管理页）。全局配置见 `frontend/AGENTS.md`。

## OVERVIEW
页面层：公开页 7 个 + admin 子域 6 个，统一 `<el-table>` + `v-loading` + ElMessage 反馈，错误走 `e?.response?.data?.detail`。

## PUBLIC VIEWS
| 文件 | 职责 |
|------|------|
| Home.vue | 首页：宣传轮播 + 当前/即将比赛卡片列表（入口 `/competitions`） |
| Login.vue | 登录/注册 tab；注册含昵称选填；401/423/429/400/422 分状态提示；登录后按 `redirect` 跳转 |
| Competitions.vue | 比赛列表（**当前为空壳**，仅标题；列表逻辑在 Home.vue） |
| CompetitionDetail.vue | 详情：报名/撤销 + admin 审批（通过/拒绝）+ 赛程卡片 + 场次排名 + 名称显示 nickname 优先 |
| MatchPlay.vue | 对局页：WS 实时棋盘，选手只读，referee/admin 可操作；`playersText` 显示双方昵称；`isRefereeOrAdmin` 来自 auth store |
| Profile.vue | 个人中心：改昵称、建队/拉人/移除成员、我的报名、积分流水 |
| Rankings.vue | 排行榜：全局/比赛/活动三 tab，`/points/leaderboard` |

## ADMIN VIEWS
| 文件 | 职责 |
|------|------|
| AdminLayout.vue | 侧边栏布局 + `<router-view>` 出口 |
| Users.vue | 用户管理：搜索/角色筛选/状态筛选、改角色、封禁/解封、重置密码 |
| Competitions.vue | 比赛 CRUD + 状态流转按钮 + 裁判选择 + 积分规则编辑器 + 曲库 JSON |
| Points.vue | 积分发放（选用户/分值/类型/原因）+ Top20 排行榜 |
| Plugins.vue | 玩法模板管理（**静态展示**，后端 `/api/gameplay/*` 未实现） |
| Traffic.vue | 异常流量监控：汇总卡 + 失败登录柱状图 + TOP IP/用户名 + 锁定账号 + 审计日志分页；自动刷新开关（15s 刷锁定） |

## SHARED PATTERNS
- 页面级 `<el-table>` + `v-loading`；操作反馈 `ElMessage.success/error`。
- 错误统一 `e?.response?.data?.detail` 展示（`catch (e: any)`）。
- http 引入：公开页 `../api/http`，admin 页 `../../api/http`。
- 名称显示 nickname 优先：`row.nickname || row.username`（Profile 成员、CompetitionDetail 参赛者）。

## STATUS LABELS
报名：
| 值 | 标签 |
|----|------|
| pending | 待审核 |
| approved | 已通过 |
| rejected | 已拒绝 |

比赛：
| 值 | 标签 |
|----|------|
| draft | 草稿 |
| registration | 报名中 |
| ongoing | 进行中 |
| finished | 已结束 |
| cancelled | 已取消 |

## TRAPS
- `Competitions.vue` 是空壳，别误以为列表在此实现。
- `admin/Plugins.vue` 仅静态展示内置 `triangle_occupy`，无管理接口。
- `MatchPlay.vue` 硬编码三角占领组件（见 frontend/AGENTS.md TRAPS），新增玩法需改此页。
- admin 页 http 路径是 `../../api/http`（多一层 `admin/`），别写成 `../api/http`。
