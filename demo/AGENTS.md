# AGENTS.md

## 项目定位

- 这是一个单机本地运行的 Python/FastAPI + 原生 JavaScript 音游比赛计分器。
- 所有命令从仓库根目录执行；项目代码集中在 `app/`，真实入口是 `app/main/main.py`。
- Python 3.10+，运行时无数据库和前端构建步骤。

## 常用命令

```bash
python -m pip install -r app/main/requirements.txt
python app/main/main.py
python app/main/main.py --headless
```

- 默认访问 `http://127.0.0.1:8001`；程序会在 8001、8002、8003 中选择端口（8000 预留给比赛网站）。
- `--headless` 禁止自动打开浏览器，适合 API 冒烟；Windows 用户也可双击 `app/main/启动服务.bat`。

## 代码边界

- `app/main/main.py` 创建 FastAPI 应用并挂载 `app/frontend/`；`app/api/routes.py` 保存全局 `GameController`，提供 REST/WebSocket 接口。
- `app/controller/` 是无第三方依赖的游戏核心；`app/config/rules.json` 是任务和难度规则的外部来源。
- `app/frontend/` 是无框架静态页面；`app/tools/gen_test_songs.py` 在根目录生成 `test_songs.json`。
- 随机开局必须先 `POST /api/songs` 导入至少 25 首且歌名唯一的歌曲，再 `POST /api/init`。

## 易错规则

- 占领变化后的顺序不可改变：`update_activation` → `check_encirclement` → `recalc_scores` → `check_l1_energy`。
- 普通格占领不可覆盖；只有 L1 可反复争夺（score/tp 挑战）。
- **新包围系统**：连通区域 = 相邻的「未占领 + 攻击方未激活」格；被「防守方占领格 / 地图边界」完全围住时整片变为防守方地块（未激活攻击方格被吃掉）；**可多次触发**（每次占领变化后判定，单次判定内迭代到不动点）。
- **攻击方激活地块不属于包围区域**：与区域相邻即**阻断包围**（激活地块无法被围）；能源格相邻同样阻断。
- **包围开关**：攻击方持有 L1 期间包围机制整体失效（`check_encirclement` 直接返回），防守方夺回 L1 后恢复。
- 包围封闭判定：区域内每格的每个邻接格要么属于本区域、要么是防守方占领；邻接槽位缺失（地图边界）视为封闭边；攻击方未激活地块并入区域不阻断。
- **L1 能量机制**：攻击方占领 L1 立刻 +1 能量（含夺回）、持有期间每 2 分钟 +1，满 7 点直接获胜（`win_type="l1_energy"`）；防守方夺回后能量**保留、暂停积累**；旧「激活 L1 秒胜」已移除（L1 激活不再影响胜负）。
- 攻击方未激活格不计分；L1 占领本身计分（得分豁免激活，与激活无关）。
- 能源加成由 `config/rules.json` 的 `energy_bonus_by_contact` 表驱动（接触 1/2/3/≥4 → +0/+1/+2/+2 封顶），改配置需同步 `rules.py` 内置默认。
- 歌曲难度分 10 分制（Cytus II 2026 难度表）：数值为主，**Chaos/Glitch 在 13/14 档比 Hard +1**（`song_lib.level_to_score(level, type)`）；歌曲缺 `level` 或 level 非法 → 400（带下标中文错误），不得 500。
- 任务流水线：25 抽 → 按定数删最难/最简各 1 → 23 抽 20 配任务（权重）→ 固定中腹高分模板（C）贪心填 L2~L6 → **L1 最后从剩余 3 首中选定数最高一首 +10**。
- 导出日志和截图在开发模式写入 `app/exports/`；打包 exe 时写入 exe 同目录的 `exports/`。

## 验证

玩法正确性用 `tests/`（pytest）守护，修改 Python 核心后至少运行：

```bash
python -m pip install -r requirements-dev.txt   # 首次：安装 pytest（仅开发依赖）
python -m pytest tests -q                        # 玩法测试全绿
python -c "import sys; sys.path.insert(0, 'app'); from controller.task_gen import generate_tasks; from controller.game import GameController; g=GameController(); g.init(generate_tasks(42)); print('ok', len(g.cells))"
python app/tools/gen_test_songs.py --seed 1
python -c "import sys; sys.path.insert(0, 'app'); import json; from controller.song_lib import parse_song_library; d=json.load(open('test_songs.json',encoding='utf-8')); print('songs', len(parse_song_library(d)))"
```

歌曲库 API 冒烟顺序是 `POST /api/songs` 后再 `POST /api/init`；未导入歌曲库会返回 400。需要分发时运行 `pyinstaller app/packaging/build.spec --workpath app/packaging/build --distpath app/packaging/dist`，不要把 `app/packaging/build/`、`app/packaging/dist/`、`__pycache__/` 或 `app/exports/` 当作源码修改。

详细算法、API 和玩法说明见 `app/docs/plan.md`；开发计划见 `app/docs/plans/`。
