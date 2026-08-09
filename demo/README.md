# 三角占领 · 赛时控制器

单机本地运行的音游比赛实时计分系统：FastAPI 后端通过 REST/WebSocket 驱动原生 JavaScript 棋盘前端。

## 运行

需要 Python 3.10+，在仓库根目录执行：

```bash
python -m pip install -r app/main/requirements.txt
python app/main/main.py
```

浏览器访问 `http://127.0.0.1:8000`。服务会自动尝试 8001、8002；不需要浏览器时使用 `python app/main/main.py --headless`。Windows 用户可以双击 `app/main/启动服务.bat`。

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
