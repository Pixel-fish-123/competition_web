# song-library-templated-tasks - Work Plan

## TL;DR (For humans)

- **做什么**：为三角占领赛时控制器加入「外部歌曲库导入（JSON）」+「模板化任务生成」+「测试歌曲生成工具」+「规则外置配置文件」。
- **为什么**：当前任务难度是纯随机标签（`CHAOS 15+`），无法使用真实歌曲库；任务权重/难度映射硬编码在 `task_gen.py`，改规则要动代码。
- **不会做什么**：不改 `controller/game.py` 与 `controller/board.py`（游戏核心零改动）；不做规则热更新（改 `rules.json` 需重启生效）；不做 D 模板（已按用户要求删除）；不实现运行时并发占领判定。
- **工作量**：7 个实现任务 + 4 个终验任务，预计一次 `$start-work` 会话完成。
- **风险**：歌曲库 <23 首时拒绝开局是硬约束（`POST /api/init` 返回 400）；`config/rules.json` 缺失/损坏时回退内置默认并打日志告警。

## Scope

### In scope
- 新文件 `config/rules.json`：难度分值映射、16 项任务表、三模板区域权重。
- 新文件 `controller/rules.py`：规则加载器（读 `config/rules.json`，失败回退内置默认 + `logging.warning`）。
- 新文件 `controller/song_lib.py`：`Song` 结构、`parse_song_library()` JSON 校验、`generate_tasks_from_songs()` 任务流水线（23 抽不重复 → 排序 → 删最高/最低 → 21 → 得分赋权 → 模板贪心匹配）。
- 新文件 `tools/gen_test_songs.py`：随机生成 50 首测试歌曲（歌名词缀组合不重名、**分层保证覆盖全部 8 档**、类型随机），输出符合导入格式的 JSON。
- 修改 `api/routes.py`：`POST /api/songs`（导入+校验）、`GET /api/songs`、`POST /api/init` 强制歌曲库已导入（否则 400），初始化走流水线。
- 修改 `controller/task_gen.py`：`TASK_TABLE` 从 `rules.py` 加载（消除双源），`generate_tasks(seed)` 保留作为无歌曲库回退。
- 修改前端（`frontend/index.html` + `frontend/board.js`，**必要时含 `frontend/ws.js`/`events.js`**）：歌曲库导入弹窗（粘贴 JSON）、格子显示 `歌曲名 · 难度`、未导入时开局按钮提示后端错误。
- 文档同步：`三角占领_游玩说明书.md` §4.3（MM 改为正式任务）、`三角占领_赛时控制器设计文档.md` §八（MM 入池 + 任务流水线/模板/规则文件说明）。

### Out of scope (Must-NOT-Have)
- 不修改 `controller/game.py` 的任何逻辑。
- **`controller/board.py` 例外**：仅新增 `song_name`/`song_type`/`song_level` 三个元数据字段（Cell dataclass + build_cells 填充 + to_dict 输出），**不改任何游戏逻辑**（激活/包围/计分/胜利/邻接）。此例外为满足本计划验收标准（`state.board[0].song_name` 非空）与前端歌曲名显示所必需——原"零改动"假设错误，`build_cells` 会丢弃额外键。
- 不做规则运行时热更新（必须重启服务生效）。
- 不做模板 D（均衡铺开）——用户已删除。
- 不做"MM 豁免"逻辑（用户已删除该规则，MM 是普通任务之一）。
- 不初始化 git 仓库、不做版本控制操作。
- 不新增测试框架（沿用 `python -c` 冒烟 + API 手动验证）。

## Verification strategy

- **规则加载**：`python -c "import sys; sys.path.insert(0,'app'); from controller.rules import load_rules; r=load_rules(); print(len(r['tasks']))"` 期望输出 16；临时改名 `app/config/rules.json` 后再次运行，期望回退默认且不抛异常（日志有 warning）。
- **歌曲解析**：`python -c` 直接调用 `parse_song_library`，合法 50 首通过；缺 name / type 非法 / level 非法 / songs 非数组 / 空数组 / **重名** 各返回带下标与原因的中文 `ValueError`。
- **分值映射**：`level_to_score` 断言 15+→15、16→15、16+→15、15→10、14+→8、14→8、13+→6、12+→5、11+→4、10→3、10+→3、9→3、8→2、7→2。
- **流水线**：`generate_tasks_from_songs(50首, seed=42)` 断言返回 21 项、`song_name` 均非空、L1（id=0）`task_bonus==10`、无重复歌曲名、id 覆盖 0..20；重复运行同 seed 结果一致（逐格 diff_score/task_name 完全相等）。
- **模板分布**：对每个模板 A/B/C 各跑 `seed=1..10`，断言 L1（top 区域）的任务得分属于该模板 high 权重区域应得的分配（A→L1 得最高分任务；B→energy 区域承载前 6 高分中的多数；C→mid 区域承载高分），并断言每区域收到的任务数 ≤ 其容量（top≤1、mid≤9、shallow≤5、energy≤6）且总和 21。
- **API 集成**（Windows PowerShell，用 `curl.exe` 而非 `curl`）：启动 `python app/main/main.py` 后：
  - `curl.exe -X POST http://127.0.0.1:8001/api/songs -H "Content-Type: application/json" -d @test_songs.json` → 200 `{"ok":true,"count":50}`
  - 未导入时 `curl.exe -X POST http://127.0.0.1:8001/api/init -H "Content-Type: application/json" -d '{"mode":"random"}'` → 400 含"请先导入歌曲库"
  - 导入后同上 init → 200 且 `state.board[0].song_name` 非空
- **失败场景**：非法 JSON 导入 → 400 + 具体错误；歌曲库 20 首导入后 init → 400（"至少 23 首"）；开局中（started 且未 game_over）再导入 → 400。
- **测试工具**：`python app/tools/gen_test_songs.py --seed 1` → 生成 `test_songs.json`，50 首、歌名唯一、`{song.diff_score for song in parse(...)} == {2,3,4,5,6,8,10,15}`（全 8 档覆盖）；`--count 10` 生成 10 首且可被 parse 接受。
- **前端**：浏览器手动 QA——导入弹窗、粘贴 JSON、开局、格子显示歌曲名。

## Execution strategy

4 个波次，每波结束可独立验证：

1. **Wave 1 规则与核心**：`config/rules.json` + `controller/rules.py` + `controller/song_lib.py` + `controller/task_gen.py` 改造（任务 1–3）。
2. **Wave 2 API**：`api/routes.py`（任务 4）。
3. **Wave 3 测试工具**：`tools/gen_test_songs.py`（任务 5）。
4. **Wave 4 前端与文档**：前端文件 + 两份设计文档（任务 6–7）。

依赖：任务 2 依赖任务 1；任务 4 依赖任务 2；任务 5 依赖任务 2；任务 6 依赖任务 4。任务 3、5 可并行；任务 7 可在 Wave 2 后任意时间做。

## Todos

### Wave 1 — 规则与核心

- [x] 1. `config/rules.json` 新建 + `controller/rules.py` 新建：规则配置与加载器。
  - References: `D:\myproject1\demo\config\rules.json`（新建，目录不存在则创建）、`D:\myproject1\demo\controller\rules.py`（新建）、现有 `D:\myproject1\demo\controller\task_gen.py`（DIFFICULTY_TABLE/TASK_TABLE 现值）
  - 内容：
    - `difficulty_score`：`{"15+": 15, "15": 10, "14": 8, "13": 6, "12": 5, "11": 4, "9": 3, "8": 2}`（存档参考；实际判定走 `level_to_score` 区间逻辑）
    - `tasks` 16 项，名称、权重和 bonus 与当前 `config/rules.json` 完全一致；MM 是首项，所有任务都进入随机池。
    - `templates`：`{"A": {"top":"high","mid":"medium","shallow":"low","energy":"medium"}, "B": {"top":"medium","mid":"low","shallow":"medium","energy":"high"}, "C": {"top":"medium","mid":"high","shallow":"medium","energy":"low"}}`
  - `rules.py`：`load_rules() -> dict`，用 `Path(__file__).resolve().parent.parent / "config" / "rules.json"` 定位；文件缺失/JSON 损坏/缺 `tasks` 或 `templates` 键时 `logging.warning` 并返回内置默认 dict（内容与上述一致）；暴露 `RULES` 模块级缓存（首次调用后固定）。不 import `task_gen`（避免循环导入）。
  - Acceptance: `python -c "import sys; sys.path.insert(0,'app'); from controller.rules import load_rules; r=load_rules(); assert len(r['tasks'])==16 and r['tasks'][0]['name']=='达成MM' and r['tasks'][0]['bonus']==10 and set(r['templates'].keys())=={'A','B','C'}; print('ok')"` 输出 ok；临时把 `app/config/rules.json` 改名后运行同命令仍可回退且不抛异常，再改回。
  - QA happy: 正常加载，tasks 16 项、MM 首项、模板 3 键。QA failure: 文件缺失回退默认（无 traceback）；JSON 损坏同样回退。
  - Commit: 项目非 git 仓库，无提交（后续任务同，不再重复标注）。

- [x] 2. `controller/song_lib.py` 新建：歌曲结构与任务流水线。
  - References: `D:\myproject1\demo\controller\song_lib.py`（新建）、`controller/rules.py`（任务 1 产物）、棋盘层映射 `controller/board.py`（L1=0、L2=1-2、L3=3-5、L4=6-9、L5=10-14、L6=15-20）
  - 内容：
    - `@dataclass Song(name, type, level, diff_score=0, difficulty_label="")`，`__post_init__` 计算 diff_score 与 `difficulty_label = f"{type} {level}"`。
    - `VALID_TYPES = {"Glitch","Chaos","Hard"}`。
    - `level_to_score(level)` —— **必须区分 `+` 后缀，实现如下（逐条精确匹配）**：
      ```
      has_plus = level.strip().endswith("+")
      n = int(level.strip().rstrip("+"))
      if n >= 16: return 15            # 16/16+ 及以上封顶 15
      if n == 15: return 15 if has_plus else 10
      if n == 14: return 8             # 14 / 14+
      if n == 13: return 6
      if n == 12: return 5
      if n == 11: return 4
      if n in (9, 10): return 3        # 9/9+/10/10+
      if n <= 8: return 2
      return 0                          # 解析失败（ValueError 由调用方处理）
      ```
      `int()` 抛 `ValueError` 时由 `parse_song_library` 捕获并转中文错误。
    - `parse_song_library(data)`：`data` 必须 dict 且含 `songs` 非空 list；逐项校验 name 非空 str、type ∈ VALID_TYPES、level 可解析（score != 0）、**name 在库内不重复**（重复 → ValueError 带下标与重复名）；错误消息带下标与原因（中文）；返回 `list[Song]`。
    - `generate_tasks_from_songs(songs, seed=None)`：
      - 用局部 `rng = random.Random(seed)`，**所有随机操作走 rng（不调用全局 `random.seed`，避免污染服务进程状态）**。
      - `len(songs) < 23` → `ValueError("歌曲库至少需要 23 首")`。
      - `rng.sample(songs, 23)` 不重复抽取 → 每首 `_weighted_choice(rules["tasks"], rng)` 配任务，总得分 = diff_score + task_bonus。
      - 按总得分降序排序 → 删除 index 0（最高）与 index -1（最低）→ 21 个。
      - 模板：`template = rng.choice(["A","B","C"])`，从 `rules["templates"][template]` 取区域权重。
      - 区域定义（容量固定）：`top={0}`（1 格）、`mid={1..9}`（9 格）、`shallow={10..14}`（5 格）、`energy={15..20}`（6 格）。**注意：`energy` 指 L6 层（15-20），即邻接能源格的层，不是能源格本身（21-26，不参与任务）**。
      - **贪心分配算法（精确）**：权重值映射 `high=3, medium=2, low=1`；将 4 区域按 `(权重值降序, 固定顺序: energy→mid→shallow→top)` 排序；任务按得分降序逐一出队，每次放入"剩余空位 > 0 且排序最靠前"的区域中的 `rng.choice` 随机空格；该区域空位减 1；直至 21 任务全部分配。效果：高权重区域先接收最高分任务直到容量满，同权重区域按固定顺序平分。
      - 返回 21 个 `cells_data` dict，字段：`id`（0..20 各一）、`diff_score`、`difficulty_label`、`song_name`、`song_type`、`song_level`、`task_name`、`task_bonus`；**id=0 的格子**：`task_bonus` 强制 10、`task_name` 固定 `"L1源头 (固定+10)"`（song 字段保留其分配到的歌曲）。
      - `_weighted_choice(table, rng)`：接受 rng 参数（复用 task_gen 逻辑但传入 rng）。
   - Acceptance: `python -c "import sys; sys.path.insert(0,'app'); from controller.song_lib import *; s=parse_song_library({'songs':[{'name':f'S{i}','type':'Chaos','level':str(8+(i%8))} for i in range(60)]}); d=generate_tasks_from_songs(s, seed=42); assert len(d)==21 and d[0]['task_bonus']==10 and len({x['id'] for x in d})==21 and len({x['song_name'] for x in d})==21; print('ok')"` 输出 ok。
  - QA happy: 21 项、id 0..20 各一、song_name 非空且唯一、L1 bonus 10、同 seed 两次结果逐格相等（evidence: 两次输出 diff 为空）。QA failure: 20 首调用 → ValueError 含"至少 23 首"；`parse_song_library` 非法输入（缺 name/type 非法/level 非法/空 songs/重名）→ 带下标中文错误。
  - 验证命令输出写入 `.omo/evidence/song_lib.txt`。

- [x] 3. `controller/task_gen.py` 改造：任务表改从 `rules.py` 加载。
  - References: `D:\myproject1\demo\controller\task_gen.py`（83 行，`TASK_TABLE` 常量 9 项）
  - 内容：任务表由 `from .rules import RULES` 提供（当前 16 项）；`_weighted_choice` 保留；`DIFFICULTY_TABLE` 保留；`generate_tasks(seed)` 仍生成 21 项并固定 L1 +10。
  - Acceptance: `python -c "import sys; sys.path.insert(0,'app'); from controller.task_gen import TASK_TABLE; assert len(TASK_TABLE)==16 and TASK_TABLE[0]['name']=='达成MM'; from controller.task_gen import generate_tasks; assert len(generate_tasks(1))==21; print('ok')"` 输出 ok。
  - QA happy: TASK_TABLE 16 项、首项为达成MM；generate_tasks 仍 21 项。QA failure: rules.json 缺失时 task_gen 仍可 import（回退默认）。
  - 验证命令输出写入 `.omo/evidence/task_gen.txt`。

### Wave 2 — API

- [x] 4. `api/routes.py` 改造：歌曲库导入/查看 + init 强制歌曲库。
  - References: `D:\myproject1\demo\api\routes.py`（146 行：`InitReq(mode, cells_data, seed)`、`api_init` L65-72 调 `generate_tasks`）
  - 内容：
    - 模块级 `_songs: list | None = None`（当前歌曲库，`Song` 列表或 None）。
    - `POST /api/songs`：body 接收 `Dict[str, Any]`（FastAPI `Body` 或直接类型标注）；`parse_song_library` 校验；失败 → `400 {"ok": False, "error": "<具体错误>"}`；成功 → `_songs = songs`，返回 `{"ok": True, "count": len(songs)}`。若 `game.started and not game.game_over` → 400 "开局中禁止覆盖歌曲库"。
    - `GET /api/songs`：返回 `{"songs": [{"name","type","level","diff_score"}...], "loaded": _songs is not None}`。
    - `api_init`：若 `req.mode == "custom" and req.cells_data` 保持原逻辑（`game.init(req.cells_data)`）；否则若 `_songs is None` → 400 "请先导入歌曲库"；否则 `game.init(generate_tasks_from_songs(_songs, req.seed))`。
    - `game.py` 不改：`GameController.init(cells_data)` 已接受 21 项 cells_data（extra 键如 song_name 被 `board.build_cells` 忽略——`build_cells` 只读已知键，见 `controller/board.py` L94-101）。
  - Acceptance: 无歌曲库 `POST /api/init {"mode":"random"}` → 400 含"请先导入歌曲库"；`POST /api/songs`（50 首）→ 200 count=50；再 `POST /api/init` → 200 且 `state.board[0].song_name` 非空。
  - QA happy: 导入→开局→`GET /api/state` 检查 board 有 song_name。QA failure: 非法 songs JSON → 400 带中文错误；20 首导入后 init → 400 带"至少 23 首"；开局中再导入 → 400。
  - 验证：启动服务后 `curl.exe` 命令（注意 **`curl.exe` + `-H "Content-Type: application/json"`**，PowerShell 中 `curl` 是别名）记录到 `.omo/evidence/api.txt`。

### Wave 3 — 测试工具

- [x] 5. `tools/gen_test_songs.py` 新建：随机测试歌曲生成器。
  - References: `D:\myproject1\demo\tools\gen_test_songs.py`（新建，`tools/` 目录不存在则创建）、`controller/song_lib.py` 的 `parse_song_library`（生成物必须可被其接受）
  - 内容：
    - 歌名词缀池：前缀 `["Neon","Crimson","Void","Stellar","Phantom","Chrono","Azure","Hyper","Solar","Crystal","Obsidian","Electric","Silent","Frozen","Inferno","Astral"]`，后缀 `["Requiem","Pulse","Horizon","Reverie","Storm","Echo","Nova","Burst","Mirage","Symphony","Sanctum","Velocity","Prism","Rapture","Genesis","Paradox"]`，组合 `f"{pre} {suf}"`；组合池 256 个 > 50 天然不重名；`--count` 超过组合池时追加数字后缀（如 `"Neon Pulse 2"`）保证唯一。
    - 难度池（加权，中档为主）：`[("15+",1),("16",1),("16+",1),("15",2),("14+",2),("14",2),("13+",3),("13",3),("12+",3),("12",3),("11+",2),("11",2),("10",2),("10+",2),("9+",2),("9",2),("8",2)]`。
    - **分层保证 8 档覆盖**：先为 8 个分值档（15/10/8/6/5/4/3/2）各保留 1 首（从对应 level 池中选），其余 `count - 8` 首随机加权抽取。
    - 类型：`rng.choice(["Glitch","Chaos","Hard"])`。
    - CLI：`argparse`，`--count`（默认 50）、`--output`（默认 `test_songs.json`，写到 `D:\myproject1\demo\test_songs.json`）、`--seed`（默认 None）；内部用 `random.Random(seed)`。
    - 生成后自检：`parse_song_library(json.loads(...))` 通过且 8 档全覆盖才写文件；否则重试（最多 5 次，重试失败则打印错误退出码 1）。
  - Acceptance: `python app/tools/gen_test_songs.py --seed 1` → 创建 `test_songs.json`；`python -c "import sys; sys.path.insert(0,'app'); import json; d=json.load(open('test_songs.json',encoding='utf-8')); assert len(d['songs'])==50; assert len({s['name'] for s in d['songs']})==50; from controller.song_lib import parse_song_library; songs=parse_song_library(d); assert {s.diff_score for s in songs}=={2,3,4,5,6,8,10,15}; print('ok')"` 输出 ok。
  - QA happy: 50 首、歌名唯一、8 档全覆盖、可被 parse。QA failure: `--count 300`（超组合池）仍生成 300 首且歌名唯一（追加数字后缀，evidence: 唯一性断言通过）；`--count 5` 生成 5 首且 8 档断言应跳过（不足 8 首时仅断言可解析与歌名唯一）。
  - 验证命令输出写入 `.omo/evidence/gen_test_songs.txt`。

### Wave 4 — 前端与文档

- [x] 6. 前端改造：歌曲库导入 UI + 歌曲名渲染。
  - References: `D:\myproject1\demo\frontend\index.html`（顶栏 L27 `init-random` 按钮、L56-66 l1-modal 的 modal/modal-box 样式可复用）、`frontend/board.js`（L86 `diffLabel = cell.difficulty_label || ...`、L90-94 renderBoard innerHTML）、`frontend/ws.js`（`apiPost` 全局函数定义、`#init-random` 点击处理器所在位置——**先 grep 确认 `init-random` 处理器在哪个文件，若在 ws.js/events.js 则一并修改该文件**）
  - 内容：
    - index.html：顶栏 controls 内「随机开局」前加 `导入歌曲库` 按钮（id=`import-songs`，class `act`）；新增模态框（复用 l1-modal 的 modal/modal-box 类）含 `<textarea id="songs-json" style="width:100%;height:200px;background:#111;color:#eaeaea;font-family:monospace;border:1px solid #333">`、取消/确认按钮（id=`songs-cancel-btn`/`songs-confirm-btn`）。
    - board.js（或处理器所在文件）：`renderBoard` 中 `diffLabel` 改为 `cell.song_name ? cell.song_name + " · " + cell.difficulty_label : (cell.difficulty_label || ("CHAOS " + cell.diff_score))`；导入流程：`#import-songs` 点击 → 显示模态框；确认 → `try { const data = JSON.parse(textarea.value); apiPost("/api/songs", data); } catch(e) { alert("JSON 格式错误: " + e.message); }`；`apiPost` 成功回调 alert 提示歌曲数量并 `refreshState()`，失败回调 alert 后端 `error` 字段且**不关闭弹窗**。
    - 「随机开局」点击处理：调用 `apiPost("/api/init", {mode:"random"})`；若返回 400（后端 error 字段如"请先导入歌曲库"），alert 该错误——在现有处理器中补充 400 分支（若现有处理器无错误处理，在 `init-random` 处理器所在文件添加）。
    - 不新增 CSS 文件；`style.css` 已有 `.modal-box`/`.modal`/`.act` 样式则复用，textarea 用内联样式（如上）。
  - Acceptance: 浏览器打开 `http://127.0.0.1:8001`，点「导入歌曲库」→ 粘贴 `test_songs.json` 内容 → 确认 → alert 显示成功数量；点「随机开局」→ 棋盘 21 格显示 `歌曲名 · 难度` 格式；不导入时点开局 → alert 显示"请先导入歌曲库"。
  - QA happy: 导入成功提示 + 棋盘歌曲名渲染。QA failure: 粘贴**语法非法** JSON → 客户端 alert "JSON 格式错误"（弹窗不关闭）；粘贴**语法合法但歌曲字段非法** JSON → 后端 400 中文错误 alert（弹窗不关闭）；无歌曲库开局 → alert 提示先导入。
  - 验证：浏览器手动操作记录 `.omo/evidence/frontend.txt`（如环境可用 Playwright 截图存 `.omo/evidence/frontend.png`）。

- [x] 7. 文档同步：MM 正式任务 + 任务流水线 + 规则文件说明。
  - References: `app/docs/plan.md` §15 与 §8.3 的当前 16 项任务表，以及 `app/config/rules.json`。
  - 内容：
    - `app/docs/plan.md`：同步当前 16 项任务、权重和 bonus；删除旧版合并任务表与过期速查表；保留任务流水线、模板和规则文件说明。
    - AGENTS.md：在关键规则区注明任务表由 `app/config/rules.json` 提供，MM 为普通任务且无豁免逻辑。
    - Acceptance: `app/docs/plan.md` 中任务表与 `app/config/rules.json` 一致，且根目录 `AGENTS.md` 引用 `app/config/rules.json`。
  - QA happy: 文档 grep 断言。QA failure: 残留旧文案（grep 命中）→ 修复后再查。
  - 验证命令输出写入 `.omo/evidence/docs.txt`。

## Final verification wave

- [x] F1. 计划合规审计：对照本计划逐一核对 7 个实现任务产物存在、Acceptance 命令均可执行输出预期（evidence: `.omo/evidence/*.txt` 全部存在且内容匹配）。
- [x] F2. 代码质量复查：`lsp_diagnostics` 检查 `controller/song_lib.py`、`controller/rules.py`、`api/routes.py`、`tools/gen_test_songs.py` 无 error；`game.py`/`board.py` 未被改动（用文件 mtime 与内容抽查确认）。
  - [x] F3. 真实手动 QA：启动 `python app/main/main.py`，走完整链路：`app/tools/gen_test_songs.py` 生成 → 浏览器导入 → 开局 → 观察歌曲名渲染 → 占领一格 → 分数变化；同时验证 400 场景（无库开局、非法 JSON、开局中再导入）。
- [x] F4. 范围保真审计：确认 `game.py`、`board.py` 零改动；无 D 模板；无 MM 豁免逻辑；`app/config/rules.json` 存在且 16 任务、3 模板；`app/tools/gen_test_songs.py` 存在且可运行。

## Commit strategy

项目当前**不是 git 仓库**（环境确认）。本计划不初始化 git、不做任何版本控制操作。若用户后续要求版本管理，再单独规划。

## Success criteria

1. `POST /api/songs` 可导入合法歌曲库（50 首），非法输入返回带下标的中文错误（含重名检测）。
2. `POST /api/init` 无歌曲库时返回 400；有歌曲库时生成 21 格任务，每格含 `song_name`、`difficulty_label`（`歌曲名 · 类型 难度`）、任务与加分。
3. 流水线正确：23 抽不重复 → 删最高/最低 → 21；L1 固定 +10；同 seed 可复现。
4. 三个模板 A/B/C 按区域权重贪心匹配（top=1/mid=9/shallow=5/energy=6 容量约束），等概率抽取；每区域任务数 ≤ 容量且总和 21。
5. 达成MM 是任务表正式成员（weight 2, bonus 10），无任何"豁免"逻辑。
6. `tools/gen_test_songs.py` 可生成 50 首不重名、**8 档全覆盖**、可导入的测试歌曲。
7. `config/rules.json` 承载难度映射/任务表/模板权重；缺失或损坏时系统回退内置默认并告警，不崩溃。
8. 前端可导入歌曲库并显示歌曲名；`game.py`/`board.py` 零改动。
9. `level_to_score` 边界正确：15+→15、16→15、15→10、14/14+→8、13/13+→6、12/12+→5、11/11+→4、9/9+/10/10+→3、≤8→2。
