# frontend-display-polish - Work Plan

## TL;DR (For humans)

- **做什么**：优化三角占领前端棋盘的显示——格子放大、字体更清晰（允许分行）、歌名不再全大写、中间格子改为三层清晰布局（歌名/难度/任务）。
- **为什么**：当前格子 96×82px 偏小；歌名拼进 Bebas Neue 字体（该字体只有大写字形）导致全大写；任务字 9px 太小且 `nowrap+ellipsis` 不换行。
- **不会做什么**：不改任何后端/游戏逻辑（`controller/*`、`api/*` 零改动）；不改导入流程、不改计分/激活/包围规则；不新增字体或外部资源。
- **工作量**：3 个实现任务 + 4 个终验任务。
- **风险**：低。纯 CSS/JS 渲染层改动；fallback（无歌曲库）路径需保持兼容。

## Scope

### In scope
- `frontend/style.css`：格子尺寸、三栏宽度、新增 `.cell-song` 类、任务字允许换行、各 owner 状态色同步。
- `frontend/board.js`：`renderBoard` 拆分歌名/难度/任务三层渲染。
- `frontend/events.js`：hover 详情补 `song_name` 行。

### Out of scope (Must-NOT-Have)
- 不修改 `controller/*`、`api/*`、`tools/*` 任何文件。
- 不修改 `main.py`、`requirements.txt`。
- 不改游戏规则（计分/激活/包围/胜利/任务表）。
- 不新增外部字体/CDN/库（仅用现有 Google Fonts：IBM Plex Sans / Bebas Neue / IBM Plex Mono）。
- 不做响应式移动端适配（当前桌面布局不变）。

## Verification strategy

- **JS 语法**：`node --check frontend/board.js frontend/events.js frontend/panel.js frontend/ws.js` → 全部 exit 0。
- **CSS 完整性**：grep `\.cell-song` 在 `style.css` 与 `board.js` 均存在；grep 确认 `.cell` 尺寸为 120px×104px；grep `#main` 列为 220px 1fr 240px。
- **浏览器手动 QA**：启动 `python app/main/main.py` → 导入 `test_songs.json` → 随机开局 → 检查：
  - 格子明显变大（120×104）
  - 歌名显示为**正常大小写**（如 `Chrono Velocity`，非全大写），字体为 IBM Plex Sans
  - 歌名过长时换行不溢出
  - 任务字清晰且允许两行
  - 三层结构：歌名 / 难度标签 / 任务要求 垂直分布
  - hover 详情面板显示歌名
- **fallback 兼容**：不导入歌曲库时（custom mode 或直接 init），格子仍正常显示难度标签（无 `undefined`）。
- 证据路径：`.omo/evidence/frontend_display.txt` + 截图（可选 `.omo/evidence/frontend_display.png`）。

## Execution strategy

单波次（3 任务可并行，均改不同区域：style.css / board.js / events.js）：
- 任务 1：`style.css`（格子/布局/新类/状态色）
- 任务 2：`board.js`（renderBoard 三层渲染）
- 任务 3：`events.js`（hover 详情歌名行）

依赖：任务 2 依赖任务 1（`.cell-song` 类）；任务 3 独立。终验波 F3 依赖全部实现任务。

## Todos

- [x] 1. `frontend/style.css`：格子放大 + 三栏调整 + `.cell-song` 新类 + 任务字换行 + 状态色同步。
  - References: `D:\myproject1\demo\frontend\style.css`（当前 422 行）——`.cell` L214-215（96×82px）、`#main` L156-162（240px 1fr 260px）、`.cell-diff` L233-239（Bebas Neue 17px）、`.cell-task` L240-250（9px + nowrap + ellipsis）、`.cell-score` L251-259（11px）、owner 状态色 L267-307
  - 内容：
    - `.cell`：`width: 120px; height: 104px; padding: 8px;`
    - `#main`：`grid-template-columns: 220px 1fr 220px;`
    - 新增 `.cell-song`：`font-family: "IBM Plex Sans", "Microsoft YaHei", sans-serif; font-size: 14px; font-weight: 500; color: var(--text); line-height: 1.25; text-align: center; word-break: break-word; overflow-wrap: anywhere; max-width: 100%;`
    - `.cell-diff`：改为 `font-size: 16px;`（保留 Bebas Neue，仅用于难度标签如 `Chaos 16+`）
    - `.cell-task`：`font-size: 10.5px; white-space: normal; line-height: 1.4; max-width: 100%; overflow: visible; text-overflow: clip;`
    - `.cell-score`：`font-size: 12px;`
    - owner 状态色：`.owner-defender .cell-song`、`.owner-attacker.activated .cell-song`、`.owner-attacker:not(.activated) .cell-song` 三个新增规则（颜色沿用对应 `.cell-diff` 的色值）
  - Acceptance: `node --check` 不适用（CSS）；grep 断言：`grep "width: 120px" frontend/style.css` 命中；`grep "220px 1fr 220px" frontend/style.css` 命中；`grep "\.cell-song" frontend/style.css` 命中。
  - QA happy: 浏览器打开后格子明显变大、歌名正常大小写、长歌名换行。QA failure: `#main` 或 `.cell` 尺寸未生效（grep 未命中）→ 修复。
  - 证据输出写入 `.omo/evidence/frontend_display.txt`。

- [x] 2. `frontend/board.js`：renderBoard 三层渲染（歌名/难度/任务）。
  - References: `D:\myproject1\demo\frontend\board.js`（当前 170 行）——`renderBoard` L86-94（当前 `diffLabel` 拼接歌名+难度）
  - 内容：`renderBoard` 中 `.cell-diff` 只放难度标签，歌名单独放 `.cell-song`：
    ```js
    const songEl = cell.song_name ? `<div class="cell-song">${cell.song_name}</div>` : "";
    const diffLabel = cell.difficulty_label || ("CHAOS " + cell.diff_score);
    el.innerHTML = `
      <div class="cell-score">${cell.total_score}${bonusTag}</div>
      ${songEl}
      <div class="cell-diff">${diffLabel}</div>
      <div class="cell-task">${taskShort}</div>
    `;
    ```
    （`songEl` 为空字符串时歌名行不渲染，fallback 兼容）
  - Acceptance: `node --check frontend/board.js` → exit 0；grep `cell-song` 命中。
  - QA happy: 浏览器显示三层结构（歌名在上、难度在中、任务在下）；无歌曲库时歌名行消失、其余正常。QA failure: 歌名仍拼在 cell-diff（grep `song_name + " · "` 命中）→ 修复。
  - 证据输出写入 `.omo/evidence/frontend_display.txt`。

- [x] 3. `frontend/events.js`：hover 详情补 `song_name` 行。
  - References: `D:\myproject1\demo\frontend\events.js`（当前 56 行）——`onCellHover` L37-46（`diffLabel` 不含 song_name）
  - 内容：`onCellHover` 中，在 diffLabel 前加：
    ```js
    const songLine = cell.song_name ? `<div style="color:var(--text);font-weight:600">${cell.song_name}</div>` : "";
    ```
    并插入 `detail.innerHTML` 顶部（`L${layer} · 格${idx}` 行之后、diffLabel 之前）。
  - Acceptance: `node --check frontend/events.js` → exit 0；grep `song_name` 在 events.js 命中。
  - QA happy: 悬停格子时详情面板第一行显示歌名。QA failure: 歌名未显示（grep 未命中或逻辑缺失）→ 修复。
  - 证据输出写入 `.omo/evidence/frontend_display.txt`。

## Final verification wave

- [x] F1. 计划合规审计：3 个实现任务产物存在（style.css/board.js/events.js 均已修改），全部 Acceptance grep/node 命令通过。
- [x] F2. 代码质量复查：`node --check` 全部前端 JS 通过；`controller/*`、`api/*`、`tools/*` 未被改动（mtime 或内容抽查）；无 TODO/FIXME 残留。
- [x] F3. 真实手动 QA：启动 `python app/main/main.py` → 浏览器走完整流程（导入→开局→检查格子尺寸/歌名大小写/换行/三层结构/hover 详情）。
- [x] F4. 范围保真审计：确认后端零改动；`style.css` 中 `.cell` 120×104、`#main` 220px 1fr 220px；无新增外部资源；fallback 路径兼容（无 `undefined`）。

## Commit strategy

项目当前**不是 git 仓库**。本计划不初始化 git、不做版本控制操作。

## Success criteria

1. 格子从 96×82px 放大至 120×104px，中央棋盘区更宽敞（三栏 220/1fr/220）。
2. 歌名以**正常大小写**显示（非 Bebas Neue 大写），长歌名换行不溢出。
3. 任务字清晰（10.5px）且允许两行显示（去掉 nowrap+ellipsis）。
4. 中间格子为三层结构：歌名 / 难度标签 / 任务要求。
5. hover 详情面板显示歌名。
6. fallback（无歌曲库）模式兼容：无 `undefined`、歌名行不渲染。
7. 后端与游戏逻辑零改动。
