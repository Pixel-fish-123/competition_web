# 三角占领 · 代码结构与规则映射（structure.md）

> 用途：把「规则」从代码里按领域**分离**出来，方便对照分析。本文件不修改代码，只做
> 「规则 → 实现位置」的索引与说明。行号以当前源码为准，若代码改动请同步更新。
>
> 关联文档：完整算法与玩法见 `plan.md`；成绩上传协议见 `成绩上传协议.md`。

---

## 一、文件总览（职责 → 规则域）

| 文件 | 职责 | 承载的规则域 |
|------|------|--------------|
| `controller/board.py` | Cell 结构、27 格邻接、地图构建 | A 棋盘结构 |
| `controller/game.py` | 占领/激活/包围/计分/胜利/时间 全流程 | B/C/D/E/F/G/L |
| `controller/song_lib.py` | 歌曲校验、level→分值、23→21 任务分配 | H/I |
| `controller/task_gen.py` | 无歌曲库时的回退任务生成 | I |
| `controller/rules.py` | 规则数据加载（含内置默认回退） | J |
| `config/rules.json` | 难度映射 / 任务表 / 模板权重 / 歌曲难度权重（数据源） | J |
| `api/routes.py` | REST/WS + 成绩上传协议 v1 的校验规则 | K |
| `main/main.py` | 入口：端口选择、浏览器、自动退出 | —（基础设施） |
| `frontend/*` | 棋盘渲染与人工操作 UI | —（展示层） |
| `tests/` | pytest 玩法正确性测试（test_board/test_game/test_song_lib/test_rules/test_task_gen） | 全部规则域（验证） |

**结论**：规则逻辑集中分布在 `game.py`（运行时规则）与 `song_lib.py`/`task_gen.py`（生成期规则）
两处；`rules.json` 是唯一的外部数据源；`routes.py` 额外承载上传协议的「严格任务校验」。

---

## 二、规则域拆分（按领域分离）

### A. 棋盘结构规则
- **27 格** = 21 个任务格（id 0–20，id 0 为 L1 源头）+ 6 个能源格（id 21–26，第 7 层）。
- 层级换算：`board.py:44-54`（`_layer_index_to_id` / `_get_layer_and_index`）。
- 邻接关系（三角网格上下左右 + 第 6 层连能源格）：`board.py:57-85`（`_compute_neighbors`）。
- 格构建与自定义校验：`board.py:96-130`（`build_cells`）。
- 常量：`MAX_PLAYABLE_CELL_ID = 20`（`game.py:10`），即普通操作只作用于 id 0–20。

### B. 占领规则
- 普通格占领入口：`game.py:131-164`（`occupy`）。
  - 已占格不可覆盖（`owner is not None` 直接忽略）；同阵营重复占领也忽略。
  - 占领后 `activated=False`，随后触发更新链。
- L1 挑战：`game.py:166-205`（`_occupy_l1`）。
  - 必须带 `score`；**优先比 score，同分比 tp**，更高才易主；L1 可随时被任何一方挑战。
  - **攻击方得手：立刻 +1 能量**（含夺回）并重置持有计时基准；满 10 点直接胜利（`_l1_victory`）。
- 清除占领：`game.py:217-238`（`cancel_occupy`）。
  - 清除 L1 时其 `l1_high_*` 纪录一并重置；已积累能量保留（暂停）。
- 输入校验：`cell_id` 须在 0–20，`team` 仅 `defender/attacker`（`game.py:135-140`）。

### C. 激活规则
- 实现：`game.py:270-291`（`update_activation`）。
- 攻击方格子只有被**能源格连通**才 `activated=True`；激活状态每次占领变化后整体重算。
- 未激活的攻击方格**不计分**（见 E）。**L1 激活不再影响胜负**（旧顶端直胜已移除）。

### D. 包围规则（新包围系统）
- 实现：`game.py:288-359`（`check_encirclement`）、`game.py:361-380`（`_region_enclosed`）。
- **连通区域** = 相邻的「未占领 + 攻击方未激活」格；排除能源格（21–26）；**攻击方激活地块不属于区域**（与区域相邻则阻断包围）；**L1（id 0）可属于区域**，但转换时豁免（不变成防守方地块）。
- **封闭判定**：区域内每格的每个邻接格，要么属于本区域，要么是防守方占领；邻接槽位缺失（=地图边界）视为封闭边。**邻接攻击方激活地块 / 能源格 → 不成立**；攻击方未激活地块不阻断（并入区域）。
- **包围失效**：攻击方持有 L1 期间 `check_encirclement` 直接返回（包围整体失效）；防守方夺回 L1 后恢复。
- **触发效果**：整片区域变为防守方地块（owner→"defender"、activated=False），分数由更新链即时重算。
- **触发时机**：每次占领变化后随更新链判定，**可多次触发**；单次判定内迭代到不动点（纯 L1 区域无可转换格时跳过）。
- 旧系统（L1 BFS / 每局一次 / 永久标记 / 退化）已删除：`encircled_cells`、`encirclement_active`、`encirclement_used` 状态与 `[包围]` 标注、前端虚线边框/蓝点均移除。

### E. 计分规则
- 实现：`game.py:331-364`（`recalc_scores`）。
- 防守方：占领即得分（`cell.total_score`），无需激活。
- 攻击方：L1（id 0）占领即得分；其余格须激活，且按连通块计 `total_score + 能源加成`。
- 能源加成：查 `config/rules.json` 的 `energy_bonus_by_contact` 表（接触 1/2/3/≥4 → +0/+1/+2/+2 封顶；缺表回退 `min(contacts-1, 2)`）——`game.py:366-383`（`_energy_bonus_for`）。
- 连通块 / 能源接触计算：`game.py:385-400`（`_bfs_attacker_block`）、`game.py:402-408`（`_count_energy_contacts`）。

### F. 胜利规则
- **L1 能量胜利**：`game.py:78-101`（`_accrue_l1_energy` / `_l1_victory`）——攻击方持有 L1 期间积累能量（占领 +1、每 2 分钟 +1），满 10 点（`L1_ENERGY_TARGET`）直接获胜（`win_type="l1_energy"`），防守方分数保留；防守方夺回后能量保留暂停。旧「激活 L1 秒胜」已移除（`check_l1_energy` 替代 `check_top_victory`，`game.py:476-478`）。
- 时间耗尽判定：`game.py:240-259`（`end_game`）——比分高者胜，平局为 draw。
- 注意「得分豁免激活 vs 能量积累」：L1 得分不依赖激活；能量积累只依赖持有。

### G. 时间规则
- 默认限时 25 分钟：`game.py:9`（`TIME_LIMIT_MINUTES`）。
- 计时：`game.py:64-71`（`elapsed` / `_sync_elapsed`）；超时：`game.py:73-78`（`_check_timeout`）。
- 设置限时：`routes.py:227-233`（`POST /api/time_limit`，须正数）；心跳：`routes.py:236-243`（`GET /api/tick`）。

### H. 歌曲 / 难度规则
- 歌曲难度分（10 分制，Cytus II 2026 难度表）：`song_lib.py:33-64`（`level_to_score(level, type)`）。
  - 数值为主：≤3→1、4-6→2、7-8→3、9-10→4、11→5、12→6、13→6、14→7、15→9、15+/16+→10；
    **Chaos/Glitch 在 13/14 档比 Hard +1**（7/8）。
- 歌曲库校验：`song_lib.py:77-110`（`parse_song_library`）——`type` ∈ {Glitch, Chaos, Hard}、歌名非空且唯一、level 合法。
- 开局最少歌曲数：**≥25 首**（`song_lib.py:178-180`）。

### I. 任务生成 / 分配规则
- 歌曲库路径（25→23→20+1 流水线）：`song_lib.py:171-270`（`generate_tasks_from_songs`）。
  1. 随机抽 25 首 → 按定数（`_song_key`，level 数值 + 加号修正）删最难/最简各 1 → 23；
  2. 23 抽 20 首，按任务表 `weight` 加权随机分配任务，按总分降序；
  3. **固定「中腹高分」模板（C，mid=high）**，按区域权重贪心填 L2~L6（容量恰 20）；
  4. L1 最后填充：剩余 3 首中定数最高一首，固定 `task_bonus=10`、`task_name="L1源头 (固定+10)"`。
- 区域定义（烈度分区）：`song_lib.py:108-125`（`_REGIONS` / `_ALLO_CAP` / `_FIXED_TEMPLATE`）。
  - `l2={1,2}` 低分、`mid={3..9}` 烈度最高、`shallow={10..14}` 次低、`energy={15..20}` 低分（L6）。
- 无歌曲库回退：`task_gen.py:38-79`（`generate_tasks`）——10 分制 8 档难度分层、顶层难度唯一化（仅一首 10 分）、L1 固定 +10。

### J. 规则数据源
- 外部数据：`config/rules.json`——难度映射（`difficulty_score`）、16 项任务表（`tasks`，含 weight/bonus）、3 模板（`templates`）、**测试歌曲难度权重池（`song_level_weights`，level→权重）**、**能源加成表（`energy_bonus_by_contact`，接触能源数→每格加成，超档封顶）**。
- 加载与回退：`rules.py:48-80`（`load_rules`，缺失/损坏时用内置 `_DEFAULT_RULES`；文件键覆盖默认、缺失键由默认补齐）。
- 注意：`rules.py` 内置默认与 `rules.json` 内容需保持一致（两处都有完整副本，`tests/test_rules.py` 有同步断言）。
- `song_level_weights` 消费方：`tools/gen_test_songs.py`（`_difficulty_pool`，配置缺失回退内置）。
- `energy_bonus_by_contact` 消费方：`game.py` 的 `_energy_bonus_for`（缺表回退 `min(contacts-1, 2)`）。

### K. 成绩上传协议规则（v1）
- 鉴权/签名/限流/去重/幂等：`routes.py:335-505`。
- 歌曲→任务格映射：`routes.py:508-510`（`_v1_find_cell`，仅在 `game.cells[:21]` 内查找）。
- **严格任务校验**：`routes.py:520-569`（`_task_issue`）——按任务名正则解析 MM / FULL COMBO / tp / 分数(万) / miss-bad-good 阈值，缺失关键字段视为不满足。
  - 开关：`STRICT_TASK_CHECK` 环境变量（`routes.py:51`），设为 `0` 可关闭。
- 单条处理（L1 挑战 / 普通格占领 / 已占忽略）：`routes.py:577-647`（`_v1_handle_item`）。
- 协议细节见 `app/docs/成绩上传协议.md`。

### L. 更新链（跨域约束，顺序不可变）
- 实现：`game.py:257-263`（`_run_update_chain`）。
- 固定顺序：`update_activation` → `check_encirclement` → `recalc_scores` → `check_l1_energy` →（未结束则 `_check_timeout`）。
- 任何占领 / 清除 / L1 挑战成功后都会触发该链，顺序颠倒会导致包围/计分结果错误。

---

## 三、比赛说明书（面向选手/裁判）

面向参赛选手与裁判的**正式规则文本**见 `规则总结.md`（《三角占领 · 比赛说明书》）。
本文件仅作开发者索引，不含玩法正文；两处内容不一致时以 `规则总结.md` 为参赛口径，
以本文件 A~L 域与源码为开发口径。

---

## 四、修改硬性约束（开发者，不得破坏）

- H1 **更新链顺序不可变**：`update_activation` → `check_encirclement` → `recalc_scores` → `check_l1_energy` → `_check_timeout`（L 域）。
- H2 **L1 机制**：得分豁免激活（B 域）；能量积累（占领 +1 / 每 2 分钟 +1 / 防守方夺回暂停保留，F 域）；能量满 **10** 胜利；攻击方持有期间包围失效（D 域）；旧「激活 L1 秒胜」已移除。
- H3 **包围语义**：区域 = 未占领 + 攻击方未激活连通分量（激活地块不属于区域）；被防守方格/地图边界完全围住即整片转换；可多次触发；**邻接激活地块 / 能源格 → 不成立**；**攻击方持有 L1 期间包围整体失效**；L1 豁免转换（D 域）。
- H4 **占领不可变**（除 L1）（B 域）。
- H5 **能源加成由 `energy_bonus_by_contact` 表驱动**（E 域），改动需同步 `rules.json` + `rules.py` 内置默认 + 测试。
- H6 **难度只看数值**，type 前缀无关（H 域）。
- H7 **歌曲库 <25 首拒绝开局**；开局中禁止覆盖歌曲库（H 域 / K 域）。
- H8 `rules.json` 缺失/损坏必须**回退内置默认、不得崩溃**；内置默认与文件保持一致（J 域，`tests/test_rules.py` 有同步断言）。
- H9 **严格任务校验语义**（缺失关键字段 = 不满足）（K 域）。
- H10 玩法正确性由 `tests/`（pytest）守护：改任何规则必须同步更新测试并全绿。
- H11 后端比赛网站玩法日志解析**兼容新旧阵营名称**（防守方/攻击方 与 守护者/掠夺者）。
