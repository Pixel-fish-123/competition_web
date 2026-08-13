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
- 普通格占领入口：`game.py:94-127`（`occupy`）。
  - 已占格不可覆盖（`owner is not None` 直接忽略）；同阵营重复占领也忽略。
  - 占领后 `activated=False`，随后触发更新链。
- L1 挑战：`game.py:129-157`（`_occupy_l1`）。
  - 必须带 `score`；**优先比 score，同分比 tp**，更高才易主。
- 清除占领：`game.py:165-186`（`cancel_occupy`）。
  - 清除 L1 时其 `l1_high_*` 纪录一并重置。
- 输入校验：`cell_id` 须在 0–20，`team` 仅 `defender/attacker`（`game.py:98-103`）。

### C. 激活规则
- 实现：`game.py:217-238`（`update_activation`）。
- 攻击方格子只有被**能源格连通**才 `activated=True`；激活状态每次占领变化后整体重算。
- 未激活的攻击方格**不计分**（见 E）。

### D. 包围规则（新包围系统）
- 实现：`game.py:241-308`（`check_encirclement`）、`game.py:310-328`（`_region_enclosed`）。
- **连通区域** = 相邻的「未占领 + 攻击方未激活」格；排除能源格（21–26）；**攻击方激活地块不属于区域**（与区域相邻则阻断包围）；**L1（id 0）可属于区域**，但转换时豁免（不变成防守方地块）。
- **封闭判定**：区域内每格的每个邻接格，要么属于本区域，要么是防守方占领；邻接槽位缺失（=地图边界）视为封闭边。**邻接攻击方激活地块 / 能源格 → 不成立**；攻击方未激活地块不阻断（并入区域）。
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
- 顶端直胜：`game.py:392-401`（`check_top_victory`）——攻击方占领 **且** 激活 L1 即胜，防守方分数保留。
- 时间耗尽判定：`game.py:188-207`（`end_game`）——比分高者胜，平局为 draw。
- 注意「得分豁免激活 vs 直胜需激活」的差异（见 §三 规则 5）。

### G. 时间规则
- 默认限时 25 分钟：`game.py:9`（`TIME_LIMIT_MINUTES`）。
- 计时：`game.py:64-71`（`elapsed` / `_sync_elapsed`）；超时：`game.py:73-78`（`_check_timeout`）。
- 设置限时：`routes.py:227-233`（`POST /api/time_limit`，须正数）；心跳：`routes.py:236-243`（`GET /api/tick`）。

### H. 歌曲 / 难度规则
- 难度分值映射（仅看数值，`type` 前缀无关）：`song_lib.py:25-55`（`level_to_score`）。
  - `15+`=15、`15`=10、`14`=8、`13`=6、`12`=5、`11`=4、`9/10`=3、`≤8`=2；≥16 归 15。
- 歌曲库校验：`song_lib.py:58-91`（`parse_song_library`）——`type` ∈ {Glitch, Chaos, Hard}、歌名非空且唯一、level 合法。
- 开局最少歌曲数：**≥23 首**（`song_lib.py:122-123`）。

### I. 任务生成 / 分配规则
- 歌曲库路径（23→21 流水线）：`song_lib.py:118-184`（`generate_tasks_from_songs`）。
  1. 随机抽 23 首不重复 → 每首按 `weight` 加权分配任务；
  2. 按 `diff_score + task_bonus` 降序，去掉最高与最低 → 剩 21；
  3. 按模板 A/B/C 的区域权重（`_REGIONS` + `_WEIGHT_MAP`）贪心分配格位；
  4. L1（id 0）固定 `task_bonus=10`、任务名「L1源头 (固定+10)」。
- 无歌曲库回退：`task_gen.py:34-75`（`generate_tasks`）——21 格难度分层、顶层难度唯一化、L1 固定 +10。
- 区域定义：`song_lib.py:108-115`（`_REGIONS` / `_WEIGHT_MAP` / `_REGION_ORDER`）。
  - 注意：`energy` 区域指第 6 层（id 15–20），**不是**能源格（id 21–26）。

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
- 实现：`game.py:209-215`（`_run_update_chain`）。
- 固定顺序：`update_activation` → `check_encirclement` → `recalc_scores` → `check_top_victory` →（未结束则 `_check_timeout`）。
- 任何占领 / 清除 / L1 挑战成功后都会触发该链，顺序颠倒会导致包围/计分结果错误。

---

## 三、游戏规则总结（单机项目）

**1. 基本盘面**：7 层三角形地图，27 格 = 21 任务格（含顶端 L1 源头）+ 6 能源格；默认限时 25 分钟，两阵营「防守方（defender）/ 攻击方（attacker）」对抗。

**2. 占领**：完成歌曲挑战可占领普通格；普通格一旦被占**不可覆盖**。L1 可反复争夺：提交 `score`（必填）+ `tp`（可选），**优先比 score，同分比 tp**。清除模式可取消占领，清除 L1 会连纪录一起重置。

**3. 激活**：攻击方的普通格只有与能源格连通才「激活」计分；未激活不计分。L1 占领本身即计分，**但**触发顶端直胜仍需激活（得分与直胜的激活要求不同）。

**4. 包围（新系统）**：防守方用己方占领格（或地图边界）把「非防守方连通区域」完全围住，区域即**整体变为防守方地块**（含攻击方格）；**可多次触发**；L1 可属于区域但**本身不被转换**。

**5. 计分**：防守方占领即得分；攻击方按激活连通块得分，能源加成 `min(接触能源数 − 1, 2)`，每格上限 +2。L1 由攻击方占领时实时加分。

**6. 胜利**：攻击方占领**并激活** L1 即「顶端直胜」；否则时间耗尽按比分定胜负，平局为 draw。

**7. 开局前提**：随机开局须先导入歌曲库（**≥23 首且歌名唯一**），顺序为 `POST /api/songs` → `POST /api/init`；难度只取数值（`type` 前缀忽略）。

**8. 任务分配**：23 首抽 23 → 加权分任务 → 按总分去掉最高/最低留 21 → 按 A/B/C 模板区域权重贪心落位；L1 固定 +10。

**9. 上传协议**：玩家设备经 `/api/v1/*` 上传成绩，令牌鉴权 + 可选 HMAC 签名 + 限流/去重/幂等；严格模式下按任务要求校验成绩（MM/FC/tp/分数/判定统计）。

**10. 测试**：`tests/`（pytest）覆盖棋盘结构 / 玩法核心（含新包围）/ 歌曲流水线 / 规则加载 / 回退生成；`python -m pytest tests -q`。
