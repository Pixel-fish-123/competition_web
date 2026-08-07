# VIEWS KNOWLEDGE BASE

**Scope:** `frontend/src/views/`（7 个公开页面 + `admin/` 4 个管理页；玩法模板页已删，issue 16）。全局配置见 `frontend/AGENTS.md`。

## OVERVIEW
页面层：公开页 7 个 + admin 子域 4 个，统一 `<el-table>` + `v-loading` + ElMessage 反馈，错误走 `e?.response?.data?.detail`。阵营标注统一「掠夺者（participant_a）/ 守护者（participant_b）」。

## PUBLIC VIEWS
| 文件 | 职责 |
|------|------|
| Home.vue | 首页：宣传插画轮播（**纯动画播放，无交互按钮**，issue 17） |
| Login.vue | 登录/注册 tab；注册含昵称选填；401/423/429/400/422 分状态提示；登录后按 `redirect` 跳转 |
| Competitions.vue | 比赛列表（完整实现，含状态/赛制/形式标签，点击进详情） |
| CompetitionDetail.vue | 详情：顶部返回键 + 报名/撤销 + admin 审批（通过/拒绝）+ 赛程卡片 + 场次排名（胜/负/平，issue 11）+ 名称显示 nickname 优先 |
| MatchPlay.vue | 对局页：WS 实时状态刷新；裁判结束比赛 → 内联判定面板（导入玩法日志自动判定 → 人工微调 → 保存结果锁定，issue 13/14）；`result_locked` 后只读 |
| Profile.vue | 个人中心：改昵称、建队/拉人/移除成员、我的报名、积分流水 |
| Rankings.vue | 排行榜：单一全局积分榜（`/points/leaderboard`） |

## ADMIN VIEWS
| 文件 | 职责 |
|------|------|
| AdminLayout.vue | 侧边栏布局 + `<router-view>` 出口（选手/比赛/积分/流量 4 项） |
| Users.vue | 用户管理：搜索/角色筛选、改角色、重置密码、删除（**无封禁/ID 列**，issue 4/12；删除提示未完结对局判对手胜，issue 3） |
| Competitions.vue | 比赛 CRUD + 状态流转 + 强制结束（issue 8）+ 任意状态可删（issue 1）；表单仅 名称/描述/头图URL/参赛形式/赛制/裁判/人数上限（issue 6） |
| Points.vue | 积分发放（选用户/分值/类型/原因，仅 admin）+ Top20 排行榜 |
| Traffic.vue | 异常流量监控：汇总卡 + 动作分布柱状图 + TOP IP/用户名 + 审计日志分页（**无锁定账号模块**，issue 15） |

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
- `MatchPlay.vue` 判定面板中：掠夺者得分=score_a（participant_a），守护者得分=score_b（participant_b）；日志分数顺序为「守护者 : 掠夺者」（logScores.defender/attacker）。
- 比赛详情/对局页有返回键（issue 10）；`router.back()` 在无历史时回退到比赛列表。
- admin 页 http 路径是 `../../api/http`（多一层 `admin/`），别写成 `../api/http`。
