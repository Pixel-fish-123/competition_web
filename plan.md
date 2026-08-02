# 萌新杯音游比赛网站 · 完整项目方案

> 版本：v1.0（待评审）｜ 日期：2026-08-02
> 目标：面向 ≤50 人规模的音游社区比赛运营平台，轻量化、易部署、本地先跑通。

---

## 一、项目概述

| 项 | 内容 |
|---|---|
| 项目名称 | 萌新杯音游比赛网站 |
| 定位 | 音游（Cytus2 等）社区比赛运营平台：宣传展示、报名、赛制编排、实时对局、积分排名 |
| 规模 | 单场比赛 ≤50 人（约 16~20 支 3 人队伍） |
| 核心特色 | 玩法模板插件系统（第一个模板 = demo「三角占领」赛时控制器） |
| 部署形态 | 单体单进程，一个端口跑全站 |

---

## 二、对原始需求的评审与修正（需求 9）

先给结论：**原始需求整体成立，但有 6 处需要修正/明确**，否则会埋坑。

### 2.1 需求 2 与 4 重叠 → 统一为「参赛单位」模型
- 问题：需求 2 说"可组队（3人）也可个人"，需求 4 又说"支持团队和个人参与，两种方式都可以作为比赛队伍参与"，两者语义重叠。
- 修正：引入 **Participant（参赛单位）** 概念——个人参赛时参赛单位 = 单个选手；组队参赛时参赛单位 = 队伍（≤3 人）。比赛配置 `participant_type`：`team`（仅队伍）/ `individual`（仅个人）/ `mixed`（混合，个人视作 1 人队伍）。赛制引擎、排名、积分全部只跟参赛单位打交道，**一套代码同时支撑两种参与方式**。

### 2.2 需求 3「小组轮换制」表述模糊 → 明确为分组循环赛
- 问题："小组轮换制"不是标准赛制术语，可理解为分组循环，也可理解为 1v1 轮换对决。
- 修正：定义三种赛制为：
  1. **分组循环赛（Round Robin）**：按配置分成若干小组，组内每两个参赛单位轮换对战一场，按胜场/净胜分排名，可配置出线名额；
  2. **瑞士轮（Swiss）**：按积分相近配对、同分匹配、不重复对阵，轮数可配（50 人建议 5~6 轮）；
  3. **单败淘汰（Single Elimination）**：标准签表，可配种子排序与季军赛。
- 每场比赛创建时选定一种赛制；三种赛制统一实现 `TournamentEngine` 接口（见 §七）。

### 2.3 需求 5 的两套积分要分清 → 双轨积分 + 可追溯流水
- 问题："奖励积分"和"活动积分"（需求 6.3）容易混为一谈。
- 修正：
  - **比赛奖励积分**：每场比赛配置积分规则（第 1 名 X 分、第 2 名 Y 分……），赛制结算后**自动**发放到参赛单位；
  - **活动积分**：管理员**手动**发放/扣除（签到、活动奖励等），带原因备注；
  - 所有积分变动写入统一的 `point_transactions` 流水表（谁、何时、为何、多少），可追溯、可回滚，排行榜数据全部由流水聚合而来，杜绝手工改库。

### 2.4 需求 6.4「异常流量检测」在 50 人规模下的正确姿态
- 问题：50 人规模上 WAF / 复杂风控是过度设计。
- 修正：聚焦四件事，全部轻量实现（见 §十）：
  1. 登录爆破防护（IP + 账号双维度限流与锁定）；
  2. API 全局限流（slowapi 中间件）；
  3. 成绩刷分校验（玩法插件 `validate_result` + 上报频率/时间窗检查）；
  4. 审计日志 + 管理后台「流量监控」页（异常登录、高频 IP、可疑 UA 聚合展示）。
- 真正的 DDoS 防护不在应用层做，交给服务器防火墙/CDN（上线方案里说明）。

### 2.5 需求 6.5 demo 无法直接嵌入 → 必须插件化改造（已确认方案）
- 现状盘点（已读 demo 源码）：
  - `GameController`（controller/game.py）：纯内存状态机，无数据库、无鉴权、无选手身份，`occupy` 只认 `defender`/`attacker` 字符串阵营；
  - `api/routes.py`：无鉴权的 HTTP + WebSocket 广播，`game` 是模块级单例；
  - 无测试、无持久化，重启即丢。
- 修正：定义**玩法模板插件规范**（§八），把 demo 改造成第一个插件 `triangle_occupy`：
  - 保留 `GameController` 核心玩法逻辑不动（规则是宝贝）；
  - 插件框架注入：比赛/对局身份、持久化、结果校验、会话生命周期；
  - 前端把 `board.js / panel.js` 等改造成 Vue 组件（或经适配层包一层），嵌入比赛对局页。

### 2.6 其余修正
- 需求 7（50 人）：SQLite 完全够用（读多写少），但**必须做定时备份**（上线方案含 cron 脚本）。
- 需求 12（轻量化）：单体单进程、无 Redis、无消息队列；WebSocket 广播用进程内连接管理器（单进程部署前提；文档注明若未来多进程部署需引入 Redis Pub/Sub）。
- 安全基线（新增）：密码 bcrypt 哈希、JWT + httpOnly Cookie、全站 HTTPS、管理端强密码建议。
- 环境风险：本机 Python 3.14.0 过新，需在 Phase 0 实测 FastAPI/Pydantic/SQLAlchemy wheel 兼容性；若报错则安装 Python 3.12 LTS（方案按 3.12 兼容写法）。

---

## 三、技术栈（需求 8）

| 层 | 选型 | 理由 |
|---|---|---|
| 后端 | Python 3.14（备选 3.12）+ FastAPI + Uvicorn | 与 demo 同栈，玩法模板可直接复用；异步性能对 50 人绰绰有余 |
| 数据库 | SQLite（WAL 模式） | 零运维、单文件备份；50 人规模读多写少完全够用 |
| ORM | SQLAlchemy 2.0 + Pydantic v2 | 主流稳定，类型安全 |
| 认证 | JWT（httpOnly Cookie）+ bcrypt | 防 XSS 窃取 token；密码强哈希 |
| 限流 | slowapi | 轻量中间件，登录爆破 + 全局限流一步到位 |
| 实时 | FastAPI 原生 WebSocket | demo 已验证此模式，无需额外依赖 |
| 前端 | Vue 3 + Vite + Pinia + Vue Router + Element Plus | 生态成熟、管理后台组件齐全 |
| 图表（可选） | ECharts | 流量监控/统计页可视化 |
| 测试 | pytest + httpx（内存 SQLite） | 轻量、无外部依赖 |
| 部署 | Docker Compose（单容器）+ Caddy（HTTPS 反代）｜ 备选 systemd 裸跑 | 见 §十四 |

> 前端**开发模式**用 Vite Dev Server + 代理；**生产模式**构建产物由 FastAPI 静态托管——单端口全站，最轻部署形态。

---

## 四、Docker 是什么 + 当前环境确认

### 4.1 Docker 的作用（一句话版）
Docker 把你的网站连同运行环境（Python、依赖、配置）打包成一个**标准集装箱（镜像）**，在任何装了 Docker 的服务器上用一条命令启动，解决"本地能跑、服务器跑不起来"的环境差异问题。`docker compose` 是它的"一键启动脚本"，可以同时拉起网站、数据库、反代等多个容器。

对本项目：容器内只装 Python + 代码 + 依赖，SQLite 数据文件通过**卷（volume）**挂载在容器外，升级代码不影响数据。

### 4.2 当前环境确认（已实测）

| 项 | 状态 |
|---|---|
| Windows 11 (24H2) | ✅ |
| Python 3.14.0 | ✅ 可用（版本过新，Phase 0 需验证依赖兼容） |
| Node.js v24.15.0 / npm 11.12.1 | ✅ 可用（前端构建用） |
| Git 2.52.0 | ✅ 可用（本项目尚未初始化仓库） |
| Docker | ❌ **未安装**（不影响本地开发；上线时在服务器上装即可，本地开发全程不需要 Docker） |

**本地开发路线**：Python 裸跑后端 + Vite 裸跑前端 → 本地跑通 → 再谈服务器部署。Docker 只出现在部署环节。

---

## 五、系统架构

```
┌─────────────────────────────────────────────────────┐
│                    浏览器（选手/裁判/管理员）          │
└───────────────┬──────────────────────┬──────────────┘
                │ HTTP/JSON            │ WebSocket（对局实时状态）
┌───────────────▼──────────────────────▼──────────────┐
│              FastAPI 单体应用（单进程单端口）          │
│  ┌───────────┐ ┌───────────┐ ┌──────────────────┐   │
│  │ 认证/权限  │ │ 比赛/报名  │ │ 玩法插件注册表     │   │
│  │ (JWT+RBAC)│ │ /赛制引擎  │ │ triangle_occupy  │   │
│  └───────────┘ └───────────┘ └──────────────────┘   │
│  ┌───────────┐ ┌───────────┐ ┌──────────────────┐   │
│  │ 积分/排行  │ │ 审计/限流  │ │ WS 连接管理器     │   │
│  │           │ │ (异常检测) │ │ (进程内广播)      │   │
│  └───────────┘ └───────────┘ └──────────────────┘   │
│                    SQLAlchemy ORM                     │
└─────────────────────────┬───────────────────────────┘
                          │
                  SQLite 单文件（WAL）
            （数据卷挂载 / 定时备份脚本）
```

**目录结构**（monorepo 单仓）：

```
competition_web/
├── backend/
│   ├── app/
│   │   ├── main.py            # 应用入口（含静态托管）
│   │   ├── config.py          # 配置（环境变量）
│   │   ├── db.py              # SQLite + SQLAlchemy 会话
│   │   ├── models/            # ORM 模型（§六）
│   │   ├── schemas/           # Pydantic 请求/响应
│   │   ├── api/               # 路由（§十三）
│   │   ├── core/              # JWT、RBAC 依赖、限流、审计
│   │   ├── services/          # 业务逻辑（报名/积分结算/…）
│   │   ├── tournaments/       # 赛制引擎（§七）
│   │   └── plugins/           # 玩法插件（§八）
│   │       ├── registry.py    # 插件扫描/注册/路由挂载
│   │       ├── base.py        # 插件接口规范
│   │       └── triangle_occupy/   # 模板一（demo 改造）
│   ├── tests/                 # pytest
│   └── requirements.txt
├── frontend/                  # Vue 3
│   └── src/
│       ├── views/             # 页面（§十二）
│       ├── stores/            # Pinia
│       ├── api/               # axios 封装
│       └── plugins/           # 玩法插件前端组件（按规范注册）
├── deploy/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── Caddyfile              # HTTPS 反代（可选）
│   └── backup.sh              # SQLite 定时备份
├── docs/
│   ├── 玩法模板开发规范.md     # 插件二次开发文档
│   └── 部署手册.md
└── plan.md                    # 本方案
```

---

## 六、数据模型（核心实体）

```
User(账号) ─┬─< TeamMember >── Team(队伍,≤3人)
            │                      │
            │                      ▼
            │              ┌─ Participant(参赛单位, 比赛内的席位)
            │              │   个人: user_id；队伍: team_id
Competition(比赛) ──< Registration(报名) ──┘
    │  状态机: 草稿→报名中→比赛中→已结束→已取消
    ├─< Round(赛轮) ──< Match(对局)
    │                        ├── 对战双方 participant_a/b
    │                        ├── gameplay_plugin + gameplay_config
    │                        └──< GameSession(玩法会话, state_json 实时落库)
    ├─< Ranking(场次排名快照) / PointsRule(积分规则)
PointTransaction(积分流水) <── 比赛结算自动 / 管理员手动(活动积分)
AuditLog(审计日志)          # IP/UA/动作/时间 → 流量监控
```

关键字段（要点，落地时细化）：
- **User**：username, email, password_hash, role(admin/referee/player), status(active/banned)
- **Team**：name, captain_id；TeamMember: team_id, user_id（≤3 人，创建后由队长添加）
- **Competition**：name, banner_url(宣传插画), description, participant_type(team/individual/mixed), tournament_format(round_robin/swiss/single_elim), format_config(JSON：组数/轮数/出线/种子…), points_rule(JSON：名次→积分), status, 时间
- **Registration**：competition_id, participant_id, status(pending/approved/rejected), approved_by
- **Match**：competition_id, round_id, participant_a/b, status(待赛/进行中/已完赛), result(胜者/比分), referee_id, scheduled_at
- **GameSession**：match_id, plugin_name, config(JSON), state_json(实时), started_at/ended_at
- **PointTransaction**：user_id, amount(±), kind(competition/activity/manual), ref_competition_id, reason, created_by

---

## 七、赛制引擎设计（需求 3）

统一抽象（`tournaments/base.py`）：

```python
class TournamentEngine(ABC):
    def __init__(self, participants: list[int], config: dict): ...
    def generate_schedule(self) -> list[RoundPlan]: ...   # 编排
    def record_result(self, match_id, result) -> None: ... # 录入结果
    def standings(self) -> list[StandingRow]: ...          # 当前排名
    def is_complete(self) -> bool: ...                     # 是否结束
    def next_round(self) -> RoundPlan | None: ...
```

三个实现：
| 赛制 | 编排规则 | 结束条件 |
|---|---|---|
| `RoundRobinEngine` 分组循环 | 组内 1v1 循环轮换（标准轮转法），支持组数配置 | 组内全对阵完成 |
| `SwissEngine` 瑞士轮 | 按积分相近配对、同分优先、不重复对阵；轮数可配（默认 ceil(log2(n))+1） | 轮数耗尽 |
| `SingleElimEngine` 单败淘汰 | 标准签表（2 的幂补位 + 种子），可配季军赛 | 决出冠军 |

- 胜负来源：对局结束时由玩法插件返回结果（`GameSession` 的 winner/比分），引擎据此推进；
- 结算：赛制结束后按 `points_rule` 自动生成积分流水 + 排名快照；
- 引擎全部**纯函数 + 依赖注入**，用 pytest 单测覆盖（轮转编排、瑞士轮配对、签表补位都要测）。

---

## 八、玩法模板插件系统（需求 6.5，核心亮点）

### 8.1 插件规范（后端契约）

每个模板是一个目录，含 `plugin.py` + `manifest.json` + 前端组件，放进 `backend/app/plugins/<name>/` 即自动注册（registry 扫描）：

```python
# base.py —— 所有模板必须实现
class GameplayPlugin(ABC):
    name: str
    version: str
    def create_session(self, match, config) -> GameSession   # 开一局
    def get_state(self, session) -> dict                     # 实时状态
    def submit_result(self, session, participant_id, payload) -> ResultReport
        # 裁判/选手上报成绩，内部调用 validate_result 防刷
    def validate_result(self, session, participant_id, payload) -> bool
        # 合法性校验：身份、时间窗、频率、值域 → 这是防刷第一道关
    def end_session(self, session) -> MatchResult            # 收局 → 胜者/比分
```

`manifest.json`：name、version、描述、所需前端组件名、路由前缀。
Registry 启动时扫描注册，并自动把 `/api/gameplay/<name>/*` 挂载进主应用，前端组件按规范自动出现在对局页。

### 8.2 模板一：triangle_occupy（demo 改造方案，已读源码）

| demo 现状 | 改造动作 |
|---|---|
| `GameController` 纯内存状态机 | 保留规则逻辑不动，包一层 `TriangleOccupyPlugin(GameplayPlugin)`；`init/occupy/…` 映射到插件方法 |
| 阵营只有 `defender/attacker` 字符串 | 插件层把对局双方 participant → 阵营映射，杜绝身份错乱 |
| 无鉴权、无身份 | 走主站 JWT 上下文：只有对局裁判（referee）和被授权者能调 `submit_result`；选手端只读 |
| 无持久化（重启丢） | `state_json` 每次变更落库；会话恢复时从快照重建 |
| `api/routes.py` 模块级单例 + WS | 会话生命周期由插件框架管理；WS 广播复用主站连接管理器 |
| 前端 board.js/panel.js/ws.js | 改造成 Vue 组件（对局面板 + 记分板），或先包 `<iframe>` 适配层过渡（Phase 5 决定，倾向直接组件化） |
| 无测试 | 补 pytest：占领/取消/包围/超时/胜者判定全流程 |

### 8.3 后续玩法模板
按 §8.1 规范新增目录即可，`docs/玩法模板开发规范.md` 提供开发指南与示例。比赛创建时从已注册模板中选择 + 配置参数。

---

## 九、权限系统（需求 6.2）

三角色 RBAC（`core/rbac.py`，权限点硬编码枚举，简单可靠）：

| 角色 | 能力 |
|---|---|
| `admin` 网站管理员 | 全部后台：用户/权限分配、比赛管理、活动积分、流量监控、玩法模板管理 |
| `referee` 比赛裁判 | 被指派比赛：创建对局、配置/开始玩法会话、录入与修正成绩、结束对局 |
| `player` 选手 | 注册、组队、报名、查看比赛/排名、个人中心 |

实现：JWT claims 携带 `role` + `user_id`；FastAPI 依赖 `Depends(get_current_user)` / `Depends(require_role("referee"))`；对局级授权（裁判只能操作自己被指派的比赛）在 service 层校验。

---

## 十、异常流量检测（需求 6.4）

轻量四件套，全部在应用层：

1. **登录爆破防护**：slowapi 对 `/api/auth/login`、`/api/auth/register` 限流（IP + 账号双维度）；连续失败 5 次锁定账号 15 分钟（写入 AuditLog + 后台提示）。
2. **API 全局限流**：全局中间件（默认 100 次/分/IP，管理端接口更严）。
3. **成绩防刷**：插件 `validate_result`（值域/顺序）+ service 层校验（对局状态必须"进行中"、上报者必须是裁判、时间窗内、频率限制）。
4. **审计与监控页**：敏感操作全部写 `AuditLog`；后台「流量监控」页聚合展示：异常登录尝试 TOP、高频请求 IP、可疑 UA、接口错误率，规则阈值可配。图表用 ECharts 或轻量表格（Phase 8 定）。

明确边界：不接 WAF、不做真实 DDoS 防护——上线文档注明交给云防火墙/服务器层。

---

## 十一、积分与排行榜（需求 5、6.3）

- **单场比赛排行榜**：由赛制引擎 `standings()` 实时生成，展示积分与明细（胜/负/净胜分）。
- **比赛奖励积分**：比赛配置 `points_rule`（如 冠军 100 / 亚军 60 / 季军 40 / 参与 10），赛制结束后自动结算 → 写入积分流水。
- **活动积分**：管理员在后台手动发放/扣除（带原因），同样走流水。
- **全局排行榜**：按用户聚合流水（比赛积分 + 活动积分，可筛选维度），独立排行榜页。
- 流水表不可直接改，只能通过系统操作产生——保证可追溯。

---

## 十二、前端页面（需求 1、5）

| 页面 | 内容 |
|---|---|
| 首页（比赛展示） | 宣传插画轮播位（图片资源位）、当前/即将比赛卡片（赛制安排摘要）、报名入口 |
| 比赛详情页 | 赛制说明、报名（个人/组队 3 人）、参赛名单、赛程/签表、对局进行页（嵌入玩法插件组件 + 实时 WS 状态）、场次排名 |
| 排行榜页 | 全局积分榜（按用户）、筛选：本场比赛/全局/积分类型 |
| 个人中心 | 资料、我的队伍（建队/邀请）、我的报名、积分流水 |
| 登录/注册 | JWT Cookie 会话 |
| 管理后台 | 选手管理（账号/封禁/角色）、比赛管理（CRUD/赛制/玩法模板/积分规则）、对局裁判面板、活动积分发放、权限分配、流量监控、玩法模板管理 |

---

## 十三、API 概要

```
/auth      register, login, logout, me
/teams     create, add_member, remove_member, my_teams
/competitions  list, detail, register, withdraw, registrations, schedule
/matches   list, detail, result(裁判录入), start_session, end_session
/rankings  competition_standings, global
/points    my_transactions, leaderboard
/admin     users, roles, points(grant/revoke), competitions CRUD,
           traffic(审计聚合), plugins(模板列表/启用), audit log
/gameplay/<plugin>/*   插件自动挂载的路由（会话操作）
/ws        对局实时状态推送（按 match_id 订阅）
/api/health  健康检查（部署用）
```

---

## 十四、上线部署方案（需求 7、11、12）

### 14.1 原则
**本地先跑通，再上服务器**（需求 11）：所有功能在本机验证通过（验收清单见 §十五 M10）后才进入部署。

### 14.2 本地运行（无 Docker）
```bash
# 后端
cd backend && python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# 前端（开发）
cd frontend && npm install && npm run dev   # 代理 /api 与 /ws 到 8000
```

### 14.3 服务器部署（两种方案）
**方案 A：Docker Compose（推荐）**
- 服务器安装 Docker + Compose；`deploy/docker-compose.yml` 单容器：构建镜像（Python 装依赖 + 前端构建产物复制进镜像）→ 启动 uvicorn → 数据卷挂载 SQLite；
- Caddy 反代提供 HTTPS（自动申请证书，比 Nginx 配置少一半）；
- `docker compose up -d` 一条命令上线；升级 = 拉新代码 + `docker compose up -d --build`。

**方案 B：裸进程 + systemd（无 Docker 备选）**
- 服务器装 Python 3.12 + Node 构建前端 → systemd 管理 uvicorn 进程 → Nginx/Caddy 反代 HTTPS。

### 14.4 上线清单（≤50 人规模）
1. 域名 + HTTPS（Caddy 自动证书；国内服务器注意备案要求）；
2. SQLite 定时备份：cron 每天 `backup.sh`（sqlite3 .backup + 保留最近 7 份）；
3. 健康检查 `/api/health` + 简单日志轮转（uvicorn access log）；
4. 密钥管理：JWT_SECRET / 管理员初始密码通过环境变量注入，不入库不入 git；
5. 服务器防火墙：仅开放 80/443（SSH 限制来源）；
6. 数据库定期 `VACUUM`（WAL 模式下可选）。

---

## 十五、Git 管理与实施步骤（需求 10）

### 15.1 Git 规范
- 仓库：在 `D:\myproject1\competition_web` 执行 `git init`（当前非 git 仓库）；
- 分支：`main`（稳定，可部署）+ `dev`（集成）+ `feature/<里程碑编号>-<功能>`（开发）；
- 流程：feature → PR/merge 进 dev → 里程碑验收通过 → merge main → 打 tag `v0.x`；
- Commit 规范：Conventional Commits（`feat:` `fix:` `docs:` `test:` `chore:`）；
- 初始化即提交：`plan.md`、`.gitignore`（.venv/node_modules/__pycache__/*.db）、骨架。

### 15.2 里程碑（一步步进行，每步可验收可回滚）

| 里程碑 | 内容 | 验收标准 |
|---|---|---|
| **M0 初始化** | git init、目录骨架、配置、requirements、依赖兼容性实测（Python 3.14） | 后端空壳启动 + `/api/health` 200；前端 vite dev 出页面 |
| **M1 账号与权限** | 注册/登录/登出、JWT、三角色、用户 CRUD | 注册→登录→角色区分生效；pytest 通过 |
| **M2 队伍与报名** | 队伍 CRUD（≤3 人）、报名流程（个人/队伍/混合）、报名审批 | 报名→审批→名单正确 |
| **M3 比赛管理** | 比赛 CRUD、状态机、赛制/玩法模板/积分规则配置 | 后台创建完整比赛配置 |
| **M4 赛制引擎** | RoundRobin / Swiss / SingleElim + 单元测试 | 三种赛制编排与结算测试全绿 |
| **M5 玩法插件系统** | 插件规范 + registry + triangle_occupy 改造（后端） | 插件可注册、会话可开可收、结果落库 |
| **M6 对局与实时** | 对局生命周期、WS 推送、裁判面板、玩法前端组件 | 对局进行中页面实时刷新、可收局 |
| **M7 积分与排行榜** | 积分规则结算、活动积分、流水、排行榜页 | 完赛自动积分 + 排行榜正确 |
| **M8 管理后台完善** | 选手管理、权限分配、流量监控、模板管理 | 后台全功能走通 |
| **M9 前端打磨** | 首页宣传展示、插画位、赛制安排展示、整体视觉 | 首页完整呈现（插画用占位图，正式图由运营提供） |
| **M10 本地联调验收** | 全链路测试 + 种子数据 + 演练 | 见下方验收清单 ✅ |
| **M11 部署上线** | Dockerfile/compose、Caddy、备份脚本、文档 | 服务器跑通、HTTPS 访问正常 |

### 15.3 本地跑通验收清单（M10）
```
选手注册×6 → 组两支 3 人队 → 管理员建比赛（混合参赛、分组循环+三角占领玩法）
→ 个人+队伍报名 → 裁判开对局 → 玩法页实时对战 → 收局 → 引擎推进下一轮
→ 赛制结束 → 自动发积分 → 排行榜/全局榜正确 → 活动积分手动发放 → 流水可查
→ 错误密码连试 6 次 → 账号锁定 + 流量监控页可见 → 管理员解封
→ 用瑞士轮、单败淘汰再各建一场比赛验证 → 备份脚本跑通
```

---

## 十六、风险清单

| 风险 | 应对 |
|---|---|
| Python 3.14 依赖兼容 | M0 首日实测；失败即装 3.12（方案按 3.12 兼容写法） |
| demo 改造工作量大（无测试/无持久化） | 规则逻辑零改动，只包适配层；改造时补测试 |
| 「小组轮换制」理解偏差 | 本方案按分组循环赛实现；如用户实指 1v1 轮换制，M4 前提出，引擎接口已预留 |
| 宣传插画等运营素材缺失 | 开发期占位图；页面预留资源位与后台可配置 |
| 无 Docker 经验 | 本地开发不需要 Docker；部署有 A/B 两方案 + 部署手册，Caddy 配置极少 |
| 国内服务器备案 | 上线前确认域名备案状态，文档提醒 |

---

## 十七、待确认事项
1. 「小组轮换制」确认按**分组循环赛**理解？（默认采用，M4 前可改）
2. 宣传插画由运营提供还是先用占位图？（默认占位图）
3. 比赛奖励积分规则示例（冠军/亚军/季军/参与各多少分）？（默认 100/60/40/10，后台可改）
4. 服务器环境（哪家云、系统版本）→ 上线前再定即可。

---

*方案完。评审通过后从 M0 开始执行。*
