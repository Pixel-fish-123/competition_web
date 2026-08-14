# encirclement-rename-tests - Work Plan

> 依据 `app/docs/整体指导建议.md` 的规则修改清单 + 用户确认的设计决策。
> 本计划是 demo 赛时控制器的一轮全流程功能迭代。

## TL;DR (For humans)

- **做什么**：
  1. **删除旧包围系统**（从 L1 BFS、每局一次、永久标记 + 退化为未占领）并实现**新包围系统**：非防守方连通区域（未占领 + 攻击方占领格）若被「防守方占领格 / 地图边界」完全围住，整片**变为防守方地块**（攻击方格被吃掉）；每次占领变化后判定、**可多次触发**；L1 继续豁免（不转换、且非防守方持有的 L1 会阻断包围）。
  2. **改名**：守护者→**防守方**、掠夺者→**攻击方**（demo 的 UI / 事件日志 / 文档全量改，`[守卫]`→`[防守]`、`守/掠`→`防/攻` 缩写）；后端玩法日志解析器**兼容新旧两套名称**（老日志仍可导入）。
  3. **新增 `demo/tests/`**：pytest 测试文件夹，专门验证玩法正确性（激活/包围/计分/L1/胜利/流水线）。
  4. **歌曲难度权重池移入 `config/rules.json`**（`song_level_weights`，gen_test_songs 不再硬编码）。
  5. **结构整理**：tests 目录、config 权重归位、全部文档同步（不重构大模块）。
- **为什么**：整体指导建议明确要求删除旧包围并换新机制；改名统一阵营称谓；此前项目零测试框架，需补玩法正确性测试；歌曲难度权重硬编码不便调整。
- **不会做什么**：不拆分 `api/routes.py`；不改成绩上传协议 v1（`/api/v1/*` 令牌/签名/幂等/限流语义不变）；不改 L1 争夺 / 激活 / 能源加成 / 顶端直胜 / 计时规则；不改根目录比赛网站的 UI 文案（仅解析器与文档同步）。
- **工作量**：7 个实现任务 + 4 个终验任务。
- **风险**：新包围是全新机制，需吃透「区域构成 / 边界判定 / 地图边界 / 不动点」语义；改名会影响后端 gameplay-log 解析（已纳入兼容方案）；前端移除旧包围状态展示需同步（state 字段删除）。

## Scope

### In scope
- `controller/game.py`：新 `check_encirclement()`（替换旧逻辑）；删除 `encircled_cells` / `encirclement_active` / `encirclement_used` 状态；`_team_cn` 改名；事件日志改名（含 `[防守]` 标注、`防/攻` 缩写）；`to_state_dict` 移除 `encircled` / `encirclement_active`。
- `app/frontend/`（index.html / style.css / board.js / panel.js / events.js）：阵营中文名全量改名；移除旧包围的展示（虚线边框/蓝点/`[包围]` 标注/`encircle-status` 面板/legend 对应项）。
- `backend/app/api/matches.py` + `backend/tests/test_gameplay_log.py`：日志解析兼容新旧名称。
- `config/rules.json` + `controller/rules.py`：新增 `song_level_weights`（测试歌曲难度权重池）。
- `tools/gen_test_songs.py`：难度权重池改从 `load_rules()` 读取（缺失回退内置）。
- 新建 `demo/tests/`（pytest）+ `demo/pytest.ini` + `demo/requirements-dev.txt`。
- 文档同步：`app/docs/plan.md`、`app/docs/structure.md`、`app/docs/规则总结.md`、`demo/AGENTS.md`、`demo/README.md`、`docs/README.md`（根，仅 demo 日志映射一句）。

### Out of scope (Must-NOT-Have)
- 不拆分 `api/routes.py`；不改上传协议 v1 语义与端点。
- 不改 `controller/board.py`（邻接/结构零改动，新包围仅用现有 `neighbors` 与「缺失邻接=地图边界」语义）。
- 不改根目录比赛网站前端文案（demo 迭代范围外）；仅解析器/测试/文档同步。
- 不改激活 / L1 争夺 / 能源加成 / 顶端直胜 / 计时规则。
- 不做规则热更新；不做模板 D；不初始化新 git 仓库（沿用根仓库）。

## 新包围系统（设计定论，用户已确认）

- **区域构成**：连通区域 = 相邻的「未占领 + 攻击方占领」格；排除能源格（21–26）。**L1（id 0）可属于连通区域**（用户确认：L1 可视为连通块的一部分），但包围转换时 **L1 本身不被占领**（豁免）。
- **封闭判定**：区域内每格的每个邻接格，要么属于本区域，要么是**防守方占领**；邻接槽位缺失（=地图边界）视为封闭边。邻接格为攻击方 / 未占领 / 能源格 → 不封闭。
- **触发效果**：整片区域变为防守方地块（owner→"defender"、activated=False）；分数由更新链 `recalc_scores` 即时重算。
- **触发时机**：每次占领 / 清除 / L1 挑战成功后随更新链判定，**可多次触发**；单次判定内迭代到不动点（纯 L1 区域无可转换格时跳过，不中断其他区域转换）。
- **L1 豁免**：L1 属于区域但不被转换；攻击方持有的 L1 在区域被围后仍保留。
- 事件日志：`包围成立！N格变为防守方地块`（type="encircle"）。

## Verification strategy

- **新包围单测**（`tests/test_game.py`，pytest）：
  - 空地连通区域被防守方格完全围住 → 整片变防守方；
  - 区域内含攻击方格 → 被「吃掉」变防守方，且分数重算计入防守方；
  - 邻接能源格 / 邻接攻击方格 / 邻接未占领格 → 不成立；
  - 贴地图边界（下方 L6 边 / 左斜边）且其余邻接全防守方 → 成立；
  - L1 属于区域但不被转换（空 L1 / 攻击方持有 L1 两种场景）；可多次触发（第二次包围仍生效）；一次判定内转换多个独立区域（共同缺口一次封住）。
- **改名断言**：grep demo 与后端不再出现「守护者」「掠夺者」（除兼容正则与历史文档外）；后端新旧格式日志各一条导入均成功。
- **歌曲权重**：`load_rules()["song_level_weights"]` 与 gen_test_songs 输出难度分布一致；rules.json 缺失时回退默认不崩溃。
- **全套验证命令**：
  ```bash
  cd demo
  python -m pip install -r requirements-dev.txt   # pytest
  python -m pytest tests -q                       # 新测试全绿
  python -c "import sys; sys.path.insert(0,'app'); from controller.task_gen import generate_tasks; from controller.game import GameController; g=GameController(); g.init(generate_tasks(42)); print('ok', len(g.cells))"
  python app/tools/gen_test_songs.py --seed 1
  node --check app/frontend/board.js app/frontend/events.js app/frontend/panel.js app/frontend/ws.js
  cd ..\backend && .venv\Scripts\python.exe -m pytest tests\test_gameplay_log.py -q   # 后端解析兼容
  ```

## Execution strategy

5 个波次：
1. **Wave 1 核心**：`game.py` 新包围 + 删旧状态 + 改名（任务 1–2）。
2. **Wave 2 前端**：frontend 5 文件改名 + 移除旧包围展示（任务 3）。
3. **Wave 3 后端兼容**：`matches.py` + `test_gameplay_log.py`（任务 4）。
4. **Wave 4 配置与测试**：`rules.json`/`rules.py`/`gen_test_songs.py` + `tests/`（任务 5–6，可并行）。
5. **Wave 5 文档**：全部文档同步（任务 7）。

依赖：任务 2、3、4 依赖任务 1（日志文案）；任务 6 依赖任务 5（song_level_weights）；任务 7 依赖 1–6。

## Todos

### Wave 1 — 核心（game.py）
- [ ] 1. 新包围系统 + 删旧包围状态 + `to_state_dict` 清理。
- [ ] 2. 改名：`_team_cn`（防守方/攻击方）、事件日志（`[防守]`、`防/攻` 缩写、顶端直胜文案）。

### Wave 2 — 前端
- [ ] 3. `frontend/` 5 文件：阵营中文名改名；移除旧包围展示（board.js encircledSet、events.js `[被包围]`、panel.js encircle-status 与截图虚线/蓝点、style.css `.cell.encircled`、index.html 包围面板与 legend 文案）。

### Wave 3 — 后端兼容
- [ ] 4. `backend/app/api/matches.py`：胜者关键字与比分正则兼容新旧；`backend/tests/test_gameplay_log.py` 补新格式用例 + 保留旧格式兼容用例。

### Wave 4 — 配置与测试
- [ ] 5. `config/rules.json` + `controller/rules.py`：新增 `song_level_weights`（内置默认同步）；`tools/gen_test_songs.py` 改从配置读取。
- [ ] 6. 新建 `demo/tests/`（pytest：test_board / test_game / test_song_lib / test_rules / test_task_gen）+ `pytest.ini` + `requirements-dev.txt`。

### Wave 5 — 文档
- [ ] 7. 同步 `plan.md` / `structure.md` / `规则总结.md` / `demo/AGENTS.md` / `demo/README.md` / 根 `docs/README.md`（demo 日志映射句）。

## Final verification wave

- [ ] F1. 计划合规审计：7 个实现任务产物存在，Acceptance 命令全部通过。
- [ ] F2. 代码质量：`node --check` 前端 4 文件；pytest 全绿；后端 `test_gameplay_log.py` 全绿；无 TODO/FIXME 残留。
- [ ] F3. 真实冒烟：启动 `python app/main/main.py`，导入歌曲库 → 开局 → 手工构造包围场景（API 冒烟）验证区域转换与比分重算；导出日志可被后端导入。
- [ ] F4. 范围保真：`board.py`、上传协议 v1、L1/激活/能源加成/计时规则零改动（mtime/内容抽查）；新旧日志格式兼容用例在。

## Commit strategy

沿用根 git 仓库（`D:\myproject1\competition_web_demo_modify`，demo 为其中一部分），按波次提交，最后推送分支并开 PR。

## Success criteria

1. 旧包围机制（L1 BFS / 每局一次 / 永久标记 / 退化）完全移除；新包围按确认语义工作且可多次触发、L1 豁免。
2. demo 全量改名：UI、事件日志、文档均为「防守方 / 攻击方」；后端可解析新旧两种格式的日志。
3. `demo/tests/` 存在且 pytest 全绿，覆盖玩法核心正确性。
4. `config/rules.json` 含 `song_level_weights`；`gen_test_songs.py` 不再硬编码难度权重。
5. 文档同步完成，`structure.md` 行号与实现一致；根仓库 PR 就绪。
