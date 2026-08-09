# 三角占领 · 赛时控制器

这是一个单机本地运行的游戏控制器：音游比赛实时计分系统。它只负责比赛现场的计分、计时、事件记录和结果裁决，FastAPI 后端通过 REST/WebSocket 驱动原生 JavaScript 棋盘前端，本身不含任何游戏画面或客户端玩法。

## 运行

需要 Python 3.10+，在仓库根目录执行：

```bash
python -m pip install -r app/main/requirements.txt
python app/main/main.py
```

浏览器访问 `http://127.0.0.1:8001`。服务会自动尝试 8002、8003（8000 预留给比赛网站）；不需要浏览器时使用 `python app/main/main.py --headless`（仅提供 API，不会自动退出，适合冒烟测试）。Windows 用户可以双击 `app/main/启动服务.bat`。

## 操作

- 顶部选择阵营（守护者 / 掠夺者 / 清除）后点击棋盘格子占领；普通格一旦被占不可覆盖。
- L1 矿脉源头可反复争夺：点击 L1 弹出计分窗口，输入分数（及可选 TP），高于当前纪录才生效。
- “清除”模式点击任意已占领格子（含 L1）可取消占领；L1 被清除后其最高纪录一并重置。
- 占领变化后自动按规则刷新：激活传播 → 包围判定 → 计分 → 顶端直胜判定，顺序不可改变。
- 随机开局前必须先导入歌曲库（至少 23 首且歌名唯一）；顶部“导入歌曲库”粘贴 JSON 即可。
- “导出日志”“截图”“结束”分别导出事件记录、保存棋盘截图、手动结束比赛。

## 开局

随机开局需要至少 23 首歌且歌名唯一。可用工具生成测试库：

```bash
python app/tools/gen_test_songs.py --count 50 --seed 1
```

在页面点击“导入歌曲库”，粘贴根目录 `test_songs.json`，再点击“随机开局”。接口调用顺序同样是先 `POST /api/songs`，再 `POST /api/init`。

## 验证

```bash
python -c "import sys; sys.path.insert(0, 'app'); from controller.task_gen import generate_tasks; from controller.game import GameController; g=GameController(); g.init(generate_tasks(42)); print('ok', len(g.cells))"
python -c "import sys; sys.path.insert(0, 'app'); import json; from controller.song_lib import parse_song_library; d=json.load(open('test_songs.json',encoding='utf-8')); print('songs', len(parse_song_library(d)))"
```

项目没有测试框架。核心实现位于 `app/controller/`，API 位于 `app/api/routes.py`，入口位于 `app/main/main.py`，规则位于 `app/config/rules.json`。完整算法和玩法说明见 `app/docs/plan.md`。

## 打包

安装 PyInstaller 后执行：

```bash
python -m pip install pyinstaller
pyinstaller app/packaging/build.spec --workpath app/packaging/build --distpath app/packaging/dist
```

生成的 `app/packaging/build/`、`app/packaging/dist/`、`__pycache__/` 和运行时 `app/exports/` 都是产物，不应提交为源码。
