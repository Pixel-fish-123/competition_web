---
slug: competition-web
status: approved
intent: clear
review_required: false
pending-action: write .omo/plans/competition-web.md
approach: FastAPI+Vue3+SQLite 单体单进程；插件化改造 demo「三角占领」为首个玩法模板；三种赛制引擎统一接口；轻量防刷四件套；M0-M11 里程碑落地
---

# Draft: competition-web

## Components (topology ledger)
| id | outcome | status | evidence path |
| --- | --- | --- | --- |
| backend FastAPI 应用 | 单端口跑全站（API+前端静态托管） | active | backend/app/main.py |
| 认证与 RBAC | JWT httpOnly Cookie + 三角色（admin/referee/player） | active | backend/app/core/ |
| 赛制引擎 | 分组循环/瑞士轮/单败淘汰 统一接口 | active | backend/app/tournaments/ |
| 玩法插件系统 | 插件规范+registry+triangle_occupy 模板 | active | backend/app/plugins/ |
| 对局与实时 | Match/GameSession 生命周期 + WebSocket 广播 | active | backend/app/services/ |
| 积分与排行榜 | 双轨积分流水 + 自动结算 + 排行榜 | active | backend/app/services/ |
| 限流与审计 | slowapi 限流 + AuditLog + 后台流量监控页 | active | backend/app/core/ |
| 前端 Vue3 | 展示页/对局页/管理后台 | active | frontend/src/ |
| 部署方案 | Docker Compose（备选 systemd）+ Caddy + 备份 | active | deploy/ |

## Open assumptions (announced defaults)
| assumption | adopted default | rationale | reversible? |
| --- | --- | --- | --- |
| Python 3.14 依赖兼容 | M0 首日实测；失败则降级 3.12 | 本机已装 3.14.0，版本过新 | yes |
| 「小组轮换制」语义 | 分组循环赛（组内轮转对阵） | 需求 3 歧义，用户已确认 | yes（M4 前可改） |
| 宣传插画 | 开发期占位图，后台可配置 | 运营素材后续提供，用户已确认 | yes |
| 奖励积分默认 | 冠军100/亚军60/季军40/参与10 | 后台可改，用户已确认 | yes |
| 部署形态 | 单进程单体，无 Redis/消息队列 | 50 人规模读多写少 | yes |

## Findings (cited - path:lines)
- demo 为 FastAPI+原生JS+WebSocket 的「三角占领」赛时控制器；GameController 是纯内存状态机，无鉴权、无持久化，阵营仅 `defender/attacker` 字符串（demo/controller/game.py:39-412）
- demo 路由为无鉴权 HTTP + WS 广播，`game` 为模块级单例（demo/api/routes.py:14-176）
- demo 无测试覆盖（codegraph 报告 reoccupy/cancel_occupy/end_game/to_state_dict 均无 covering tests）
- 本机环境：Python 3.14.0 ✅、Node v24.15.0/npm 11.12.1 ✅、Git 2.52.0 ✅、Docker ❌ 未装、Windows 11 24H2
- 工作目录 D:\myproject1\competition_web 非 git 仓库，仅存旧 plan.md 与 .codegraph/.omo

## Decisions (with rationale)
- 技术栈 FastAPI+Vue3+SQLite：与 demo 同栈，玩法模板直接复用；50 人规模读多写少，SQLite WAL 足够（用户确认）
- 插件化改造 demo：定义 GameplayPlugin 规范，规则逻辑零改动只包适配层（用户确认）
- 参赛单位（Participant）统一模型：个人=1 人队伍，一套代码双轨支持需求 2/4
- 双轨积分（比赛奖励自动 + 活动积分手动）统一走 PointTransaction 流水，可追溯
- 异常流量检测=轻量四件套：登录爆破防护、API 限流、成绩防刷、审计+监控页；不做应用层 WAF
- 部署：Docker Compose 单容器 + Caddy HTTPS + SQLite 定时备份；备选 systemd 裸跑

## Scope IN
比赛展示页/账号注册登录/3 人组队/个人与队伍双轨参赛/三种赛制引擎/场次排名/双轨积分与独立排行榜/管理后台（选手、权限分配、活动积分、异常流量监控、玩法模板）/玩法插件规范+triangle_occupy 模板/git 项目管理/本地先跑通/轻量化上线

## Scope OUT (Must NOT have)
- 不做应用层 WAF / DDoS 防护（交服务器防火墙/CDN）
- 不做支付/电商/邮件短信/第三方登录（50 人规模不需要）
- 不做 Redis、消息队列、多进程部署（单进程单体；文档注明未来扩展路径）
- 不改动 demo 核心玩法规则逻辑（只包适配层）
- 不做移动端 App

## Open questions
- ~~服务器环境（云厂商/系统版本）~~ → 已决策（2026-08-02）：观众主要在国内 → 国内轻量服务器单机部署（腾讯云/阿里云香港 2C2G 优先，免备案），弃用 Cloudflare Pages（原因：Pages 无常驻进程、Python 生态受限、WebSocket 需付费 Durable Objects、SQLite 文件不可用、国内访问慢/不稳定）；M11 部署手册含购置指引
- GitHub 仓库 → 用户创建中，创建后提供地址，M0 加 remote 推送

## Metis gap analysis (2026-08-02, bg_34d4726c, ses_03cea683bffe9lpsqm82at3sqI)
已折叠进 .omo/plans/competition-web.md todos（silent fold-in），关键修正决策：
- C1 写权限：~~选手可对己方阵营 submit_result~~ → **用户 2026-08-02 最终确认：仅 referee/admin 可操作棋盘，选手只读观看（裁判替双方操作，符合"赛时控制器"用法）——覆盖早前 C1 修正**（todo 13/18/25）
- C2 锁定阈值统一 5 次（todo 16/25）——plan.md 验收清单「连错 6 次」废弃
- C3 瑞士轮默认轮数 = min(ceil(log2(n))+1, 7)（todo 10）
- C4/E11 歌曲库来源：create_session 的 config 携带 song_lib，不再依赖全局 _songs（todo 13）
- C6/E15 队伍积分：成员各得全额，不拆分（todo 17）
- C7 对局由引擎编排生成，referee 不手工建对局（todo 14）
- E1 平局语义：循环/瑞士计 0.5；单败淘汰不允许 draw，裁判必填胜者（todo 9/10/11/14）
- E2 轮空：奇数队伍循环赛/瑞士轮 bye 计 1 胜（todo 9/10）
- E3 裁判指派：Competition.referee_ids，admin 指派，service 层校验（todo 8/14）
- E5 人数上限：Competition.max_participants 默认 50，满员 400（todo 7/8）
- E6 cancel 授权：仅可取消己方阵营格子（todo 13）
- E7 成绩防刷边界：validate_result 只做值域/顺序/频率，不做分数真实性核验（todo 13）
- E9 会话恢复：state_json 存 elapsed，恢复时 _start_ts = now - elapsed*60（todo 13）
- E12 CSRF：SameSite=Lax + Origin 校验（todo 4）
- E13 WS 鉴权 + 订阅白名单 + 消息频率限制（todo 15/16）
- E18 备份恢复演练 backup_restore_test.sh（todo 26）
- V1 引擎同分决胜规则：胜场→净胜分→相互胜负→种子 id（todo 9）；瑞士轮 积分→Buchholz→净胜分→种子 id（todo 10）
- S6 出线名额/第二阶段从 scope 移除（todo 8/9）
- S2 iframe 过渡方案废弃，直接组件化（todo 18）
- 修订项：plan.md §十五 15.3 验收清单「连错 6 次」应改 5 次、§七瑞士轮「建议 5~6 轮」与公式冲突应注明上限 7——plan.md 在写边界外，执行时由 worker 在 M10 前修订

## Approval gate
status: approved
<!-- 2026-08-02 用户对方案 4 项待确认回复「1.可以 2.可以 3.可以」并追问 GitHub 流程，即批准方案与默认项；服务器项按计划延后至 M11 前确认。Metis 差距分析完成后静默折叠修正，方案核心不变。 -->
