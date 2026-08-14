# 三角占领 · 赛时控制器

单机本地运行的音乐游戏（音游）比赛实时计分系统。它只负责比赛现场的**计分、计时、事件记录与结果裁决**，通过浏览器棋盘或玩家设备成绩上传来驱动，本身不含游戏画面或客户端玩法。

> 本项目与仓库根目录的比赛网站（`backend/` + `frontend/`）**互相独立**：网站负责报名、赛程、积分榜等业务，本控制器是比赛现场的裁决工具。请勿混用两端代码。

## 技术栈

- Python 3.10+，无数据库、无前端构建步骤
- 后端：FastAPI + Uvicorn（REST + WebSocket 实时状态推送）
- 前端：原生 HTML/CSS/JS，无框架
- 核心算法在 `app/controller/`（纯 Python，无第三方依赖）

## 玩法简述

双方阵营——**防守方（defender，蓝色）** 与 **攻击方（attacker，红色）**——在 7 层三角形地图上争夺格子。地图共 27 格：21 个任务格（id 0–20，含顶端 L1 源头）+ 6 个能源格（id 21–26，第 7 层）。默认限时 25 分钟。

- 完成歌曲挑战可占领普通格；**普通格一旦被占不可覆盖**，只有 L1 可反复争夺（比 score，同分比 tp）。
- 攻击方占领的格子需被「能源」连通才**激活**计分；未激活格不计分。
- 防守方用己方占领格（或地图边界）把一片「未占领 + 攻击方未激活」区域完全围住时触发**包围**：该区域**整体变为防守方地块**（未激活攻击方格被吃掉），**可多次触发**；攻击方**激活**地块相邻则包围无法成立；L1 属于区域但本身不被转换。
- 攻击方占领**并持有** L1 源头时积累能量（占领立刻 +1、每 2 分钟 +1）：能量满 **10 点**即「L1 能量胜利」直接获胜；防守方夺回 L1 可暂停积累；攻击方持有 L1 期间**包围机制失效**。
- 时间耗尽则比分高者胜（防 : 攻）。

完整规则与算法见 `app/docs/plan.md`。

## 运行

在 `demo/` 目录下执行（命令中的相对路径以此目录为基准）：

```bash
python -m pip install -r app/main/requirements.txt
python app/main/main.py
```

浏览器访问 `http://127.0.0.1:8001`；服务会自动尝试 8002、8003（8000 预留给比赛网站）。不需要浏览器时用 `python app/main/main.py --headless`（仅提供 API，适合冒烟测试，且不会自动退出）。Windows 用户也可双击 `app/main/启动服务.bat`。

所有浏览器标签页关闭后，控制器会在约 10 秒后自动退出（`--headless` 下禁用该看门狗）。

## 开局与歌曲库

随机开局前必须先导入歌曲库：至少 **25 首且歌名唯一**。接口顺序固定为 `POST /api/songs` 导入，再 `POST /api/init` 开局；未导入歌曲库时 `init` 返回 400。

在页面点击「导入歌曲库」粘贴 `test_songs.json` 的内容（仓库根目录内置的静态样例歌曲库），再「随机开局」。

## 两种操作方式

**1. 人工操作（裁判浏览器）**：顶部选择阵营（防守方 / 攻击方 / 清除）点击棋盘格占领；点击 L1 弹出计分窗口输入分数（及可选 TP）；「清除」模式可取消占领（含 L1，其纪录一并重置）。接口为 `/api/occupy`、`/api/cancel`、`/api/end`、`/api/time_limit`。

**2. 自动化成绩上传（协议 v1）**：玩家设备 / 机器人插件通过 `/api/v1/*` 上传单曲成绩，控制器自动完成「歌曲 → 任务格」映射、普通格占领与 L1 挑战。需先 `POST /api/init` 取得 `match` / `defender` / `attacker` 三枚令牌，用 `X-Match-Token` + `X-Team-Token` 鉴权（可选 HMAC-SHA256 签名防篡改）。协议详见 `app/docs/成绩上传协议.md`。

| 端点 | 说明 |
|------|------|
| `POST /api/v1/results` | 上传单条成绩 |
| `POST /api/v1/results/batch` | 批量上传（最多 50 条） |
| `GET /api/v1/tasks` | 当前 21 个任务格（含 L1） |
| `GET /api/v1/results/{client_msg_id}` | 查询某次上传的处理结果 |

## 主要接口

| 方法/路径 | 说明 |
|-----------|------|
| `POST /api/songs` / `GET /api/songs` | 导入 / 查询歌曲库 |
| `POST /api/init` | 开局（返回令牌与棋盘状态） |
| `POST /api/occupy`、`/api/cancel` | 占领 / 取消占领格子 |
| `POST /api/end`、`/api/time_limit` | 结束比赛 / 设置限时（分钟） |
| `GET /api/state`、`/api/tasks`、`/api/scores` | 查询状态 / 任务 / 比分 |
| `GET /api/tick` | 计时心跳（含超时判定） |
| `GET /api/events/export` | 导出事件日志（`?save=1` 落盘） |
| `POST /api/screenshot` | 保存棋盘截图（base64 PNG） |
| `WS /ws` | 状态实时推送 |

## 目录结构

```
demo/
├── README.md / AGENTS.md      # 入口文档
├── test_songs.json            # 测试歌曲库
└── app/
    ├── main/main.py           # 入口：FastAPI + 端口选择 + 自动退出
    ├── controller/            # 纯 Python 游戏核心（无第三方依赖）
    │   ├── board.py           # Cell 结构、27 格邻接、地图构建
    │   ├── game.py            # 激活/包围/计分/胜利算法
    │   ├── song_lib.py        # 歌曲校验、level→分值、23→21 模板流水线
    │   ├── task_gen.py        # 无歌曲库回退的任务生成
    │   └── rules.py           # 规则加载（config/rules.json，缺失回退内置默认）
    ├── config/rules.json      # 难度映射、16 项任务表、3 模板权重、能源加成表
    ├── api/routes.py          # REST + WebSocket + 成绩上传协议 v1
    ├── frontend/              # 原生静态页面（棋盘/面板/事件/WS）
    └── docs/                  # plan.md、成绩上传协议.md、plans/
```

## 验证

玩法正确性由 `tests/`（pytest）守护。修改 Python 核心后至少运行：

```bash
python -m pip install -r requirements-dev.txt   # 首次：安装 pytest（仅开发依赖）
python -m pytest tests -q                        # 玩法测试（含新包围/激活/计分/L1/流水线）
python -c "import sys; sys.path.insert(0, 'app'); from controller.task_gen import generate_tasks; from controller.game import GameController; g=GameController(); g.init(generate_tasks(42)); print('ok', len(g.cells))"
python -c "import sys; sys.path.insert(0, 'app'); import json; from controller.song_lib import parse_song_library; d=json.load(open('test_songs.json',encoding='utf-8')); print('songs', len(parse_song_library(d)))"
```

歌曲库 API 冒烟顺序是 `POST /api/songs` 后再 `POST /api/init`。

## 打包

安装 PyInstaller 后执行：

```bash
python -m pip install pyinstaller
pyinstaller app/packaging/build.spec --workpath app/packaging/build --distpath app/packaging/dist
```

生成的 `app/packaging/build/`、`app/packaging/dist/`、`__pycache__/` 和运行时 `app/exports/` 都是产物，不应提交为源码。打包 exe 时导出文件写入 exe 同目录的 `exports/`。

## 文档

- 代码结构与规则映射（规则→实现位置索引）：`app/docs/structure.md`
- 完整算法与玩法：`app/docs/plan.md`
- 成绩上传协议 v1：`app/docs/成绩上传协议.md`
- 开发计划：`app/docs/plans/`
