# 萌新杯音游比赛网站 (competition-web)

面向音游（Cytus2 等）社区比赛运营平台。单场比赛支持 ≤50 人，采用单体架构：FastAPI 后端 + Vue3 前端 + SQLite，单端口即可跑通全站。玩法模板采用插件化设计，demo「三角占领」作为第一个模板内置。

## 功能特性

按原始需求整理为 12 项核心能力：

1. **比赛展示页**：宣传插画位（占位图，后台可更换 `banner_url`）、当前赛制安排、报名入口。
2. **账号体系**：注册 / 登录 / 登出（JWT httpOnly Cookie + CSRF 防护）、3 人组队、个人参赛。
3. **三种赛制引擎**：
   - 分组循环赛（Round Robin）：平局计 0.5 胜、轮空计 1 胜、同分决胜。
   - 瑞士轮：默认轮数 `min(ceil(log2 n)+1, 7)`，Buchholz 决胜。
   - 单败淘汰：禁平局，裁判指定胜者，可配置种子与季军赛。
4. **个人 / 队伍双轨参赛**：参赛单位模型为「个人 = 1 人队伍」，支持混合模式。
5. **单场排名 + 奖励积分**：积分由 admin 手动发放，队伍成员各得全额；单一积分排行榜（按总积分排名）。
6. **管理后台**：选手管理、权限分配（admin / referee / player 三角色 + 比赛裁判组）、活动积分发放、异常流量监控、玩法模板管理。
7. **玩法插件系统**：`GameplayPlugin` 规范 + registry 自动注册；模板 `triangle_occupy`（demo「三角占领」赛时控制器，规则逻辑零改动适配）。
8. **异常流量检测**：登录爆破防护（5 次失败锁定 15 分钟）、API 全局限流（slowapi，429）、成绩防刷校验、审计日志 + 后台流量监控页。
9. **WebSocket 对局实时推送**：Cookie 鉴权 + 订阅白名单（参赛双方 / 裁判 / admin）+ 每连接 ≤10 msg/s 频率限制。
10. **对局操作权限**：仅 referee / admin 可操作棋盘，选手只读观看。
11. **实时对局**：三角占领棋盘玩法页（对局双方实时对战面板）。
12. **种子数据脚本**：幂等演示数据。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.14 + FastAPI + Uvicorn + SQLAlchemy 2.0 + SQLite (WAL) + PyJWT + bcrypt + slowapi |
| 前端 | Vue 3 + Vite + TypeScript + Pinia + Vue Router + Element Plus + axios |
| 测试 | pytest + httpx（后端 237 个测试全绿）；前端 vue-tsc + vite build |

## 环境要求

- Python 3.14（或 3.12+）
- Node.js ≥ 20（本机 v24）
- npm、Git
- 无需 Docker（部署阶段可选）

## 快速开始

> **一键启动**：双击根目录 `启动服务.bat`（或运行 `start.ps1`），自动完成环境准备并同时启动前后端，浏览器自动打开 http://localhost:5173。关闭服务窗口即停止。

### 1. 启动后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows；macOS/Linux 用 source .venv/bin/activate
pip install -r requirements.txt
python seed.py                 # 幂等种子数据（可选，生成演示数据）
python -m uvicorn app.main:app --port 8000 --reload
```

### 2. 启动前端（开发，另开一个终端）

```powershell
cd frontend
npm install
npm run dev                    # 默认 http://localhost:5173，代理 /api 与 /ws 到 :8000
```

### 3. 生产构建（前端产物由 FastAPI 托管，单端口）

```powershell
cd frontend
npm run build
```

构建产物按部署手册处理（`frontend/dist` 需放置到后端静态托管目录，具体以实际代码为准）。

## 默认账号（种子数据，仅开发环境！）

> ⚠️ **部署上线前必须修改默认密码！**

| 角色 | 账号 | 密码 |
| --- | --- | --- |
| 管理员 | admin | admin123 |
| 裁判 | referee | referee123 |
| 选手 | player1 .. player8 | player123 |

演示比赛：**萌新杯·演示赛**（分组循环 + 三角占领 + 积分规则）。

## 测试

```powershell
cd backend
.venv\Scripts\python -m pytest tests -q    # 237 passed
```

```powershell
cd frontend
npm run build                              # 前端类型检查 + 构建
```

## 目录结构

```
competition_web/
├── backend/
│   ├── app/
│   │   ├── api/           # 路由（auth/teams/registrations/competitions/matches/points/rankings/admin_*）
│   │   ├── core/          # 安全/RBAC/限流/锁定/审计/WS连接管理
│   │   ├── models/        # ORM 模型
│   │   ├── schemas/       # Pydantic 校验
│   │   ├── services/      # 业务逻辑（报名/对局/积分结算）
│   │   ├── tournaments/   # 三种赛制引擎（纯逻辑）
│   │   └── plugins/       # 玩法插件（registry + triangle_occupy）
│   ├── tests/             # pytest 测试
│   ├── seed.py            # 幂等种子数据
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── views/         # 页面（首页/比赛详情/对局/排行榜/个人中心/登录/admin/*）
│       ├── plugins/       # 玩法前端组件
│       ├── stores/        # Pinia
│       └── api/           # axios
├── docs/                  # 文档（部署手册 M11 阶段生成）
└── plan.md                # 项目方案与执行计划
```

## API 概览

| 路径 | 说明 |
| --- | --- |
| `/api/auth` | 注册 / 登录 / 登出 |
| `/api/competitions` | 比赛展示与报名 |
| `/api/matches` | 对局查询与操作 |
| `/api/gameplay/{plugin}` | 玩法插件对局接口 |
| `/api/points` | 积分发放与查询 |
| `/api/rankings` | 排行榜（全局 / 比赛积分 / 活动积分） |
| `/api/admin/*` | 管理后台接口 |
| `/ws` | WebSocket 对局实时推送 |

## 版本记录

- 分支：`main`（稳定）+ `dev` + `feature/*`
- 里程碑 tag：`v0.0`(M0) `v0.1`(M4) `v0.2`(M6) `v0.3`(M8/M9) `v0.4`(M10)
- M10 全链路联调验收 ALL PASS（15 项验收清单 20/20 子检查）
- 远程仓库：https://github.com/Pixel-fish-123/competition_web.git

## 部署说明

当前完成本地开发与验收（M10）。部署方案见 `docs/部署手册.md`（M11 生成中）。
