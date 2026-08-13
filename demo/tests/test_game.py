"""玩法核心测试：占领 / L1 / 激活 / 新包围系统 / 计分 / 胜利 / 更新链。

运行：cd demo && python -m pytest tests/test_game.py -q

新包围系统（整体指导建议确认）：
- 连通区域 = 相邻的「未占领 + 攻击方占领」格，排除能源格与 L1（豁免）；
- 封闭判定：区域内每格的每个邻接格都属于本区域或是防守方占领，邻接槽位缺失
  （地图边界）视为封闭边；邻接攻击方 / 未占领（含 L1）/ 能源格 → 不成立；
- 成立则整片变为防守方地块；每次占领变化后判定、可多次触发。
"""

from controller.game import GameController


def make_cells(diff: int = 10) -> list[dict]:
    data = []
    for cid in range(21):
        data.append({
            "id": cid,
            "diff_score": diff,
            "difficulty_label": f"CHAOS {diff}",
            "task_name": "测试任务",
            "task_bonus": 0,
        })
    return data


def new_game(diff: int = 10) -> GameController:
    g = GameController()
    g.init(make_cells(diff))
    return g


def owners(g: GameController) -> dict[int, str | None]:
    return {c.id: c.owner for c in g.cells[:21]}


# ---------------------------------------------------------------- 占领基础


def test_occupy_and_score():
    g = new_game()
    assert g.occupy(3, "defender")
    assert g.cells[3].owner == "defender"
    assert g.defender_score == 10.0


def test_occupy_immutable():
    g = new_game()
    assert g.occupy(3, "defender")
    assert not g.occupy(3, "attacker")   # 不可覆盖
    assert not g.occupy(3, "defender")   # 同阵营重复也忽略
    assert g.cells[3].owner == "defender"


def test_occupy_invalid():
    g = new_game()
    assert not g.occupy(25, "defender")   # 超出可操作范围
    assert not g.occupy(3, "red")         # 非法阵营


def test_cancel_occupy():
    g = new_game()
    g.occupy(3, "defender")
    assert g.cancel_occupy(3)
    assert g.cells[3].owner is None
    assert g.defender_score == 0.0
    assert not g.cancel_occupy(3)  # 空格不可再取消


# ---------------------------------------------------------------- L1 规则


def test_l1_requires_score():
    g = new_game()
    assert not g.occupy(0, "attacker")  # 缺 score
    assert g.l1_high_score is None


def test_l1_compare_score_then_tp():
    g = new_game()
    assert g.occupy(0, "defender", score=100, tp=99.0)
    assert g.l1_high_team == "defender"
    # score 更高 -> 易主
    assert g.occupy(0, "attacker", score=101, tp=0)
    assert g.l1_high_team == "attacker"
    # score 相同、tp 更高 -> 易主
    assert g.occupy(0, "defender", score=101, tp=99.8)
    assert g.l1_high_team == "defender"
    # score 相同、tp 相同 -> 先到先得（持有方不变）
    assert g.occupy(0, "attacker", score=101, tp=99.8)
    assert g.l1_high_team == "defender"
    # score 更低 -> 不变
    assert g.occupy(0, "attacker", score=50, tp=100)
    assert g.l1_high_team == "defender"


def test_l1_scores_without_activation():
    """L1 得分豁免激活：攻击方占 L1 立即加分，无需连通能源。"""
    g = new_game()
    g.occupy(0, "attacker", score=900000)
    assert g.attacker_score == 10.0
    assert g.cells[0].activated is False
    assert g.game_over is False  # 未激活 -> 不触发顶端直胜


def test_cancel_l1_resets_records():
    g = new_game()
    g.occupy(0, "attacker", score=900000, tp=99.5)
    g.cancel_occupy(0)
    assert g.l1_high_score is None
    assert g.l1_high_tp is None
    assert g.l1_high_team is None
    assert g.cells[0].owner is None


# ---------------------------------------------------------------- 激活


def test_activation_via_energy():
    g = new_game()
    g.occupy(15, "attacker")   # L6，直接邻接能源 21
    assert g.cells[15].activated
    assert g.attacker_score == 10.0


def test_unactivated_attacker_no_score():
    g = new_game()
    g.occupy(10, "attacker")   # L5，未连通能源
    assert not g.cells[10].activated
    assert g.attacker_score == 0.0


def test_activation_lost_after_cancel():
    """激活依赖连通路径；裁判取消关键格后，下游格子失去激活并停止计分。"""
    g = new_game()
    g.occupy(15, "attacker")
    g.occupy(10, "attacker")
    assert g.cells[10].activated
    assert g.attacker_score == 20.0
    g.cancel_occupy(15)
    assert not g.cells[10].activated
    assert g.attacker_score == 0.0


# ---------------------------------------------------------------- 能源加成


def test_energy_bonus_cap():
    g = new_game()
    # 2 格连通块接触 2 个能源 -> 每格 +1
    g.occupy(15, "attacker")
    g.occupy(16, "attacker")
    assert g.attacker_score == 22.0  # (10+1)*2
    # 再加 1 格，接触 3 个能源 -> 每格 +2（封顶）
    g.occupy(17, "attacker")
    assert g.attacker_score == 36.0  # (10+2)*3


def test_energy_bonus_single_block_contacts_one_energy():
    g = new_game()
    g.occupy(15, "attacker")
    assert g.attacker_score == 10.0  # 接触 1 个能源 -> +0


def test_energy_bonus_reads_from_config():
    """能源加成表由 config/rules.json 的 energy_bonus_by_contact 驱动。"""
    from controller.rules import RULES
    table = RULES["energy_bonus_by_contact"]
    g = new_game()
    assert g._energy_bonus_for(0) == 0
    assert g._energy_bonus_for(1) == int(table["1"])   # 0
    assert g._energy_bonus_for(2) == int(table["2"])   # 1
    assert g._energy_bonus_for(3) == int(table["3"])   # 2
    assert g._energy_bonus_for(4) == int(table["4"])   # 2
    assert g._energy_bonus_for(9) == int(table["4"])   # 超档封顶


# ---------------------------------------------------------------- 新包围系统


def test_enclosure_converts_empty_region():
    g = new_game()
    for cid in (1, 6, 7):              # 还差 4 未占
        g.occupy(cid, "defender")
    assert g.cells[3].owner is None    # 尚未合围
    g.occupy(4, "defender")            # 完成合围 -> 整片变防守方
    assert g.cells[3].owner == "defender"


def test_enclosure_two_pockets_one_chain():
    """一次占领同时封住两个独立区域 -> 同一更新链内双双转换。"""
    g = new_game()
    for cid in (1, 4, 6, 16, 17, 10, 12):
        g.occupy(cid, "defender")
    assert g.cells[3].owner is None    # 区域 {3,7,11} 未合围（7 空）
    assert g.cells[11].owner is None
    g.occupy(7, "defender")            # 7 是两片区域的共同缺口
    assert g.cells[3].owner == "defender"
    assert g.cells[11].owner == "defender"


def test_enclosure_captures_attacker_cells():
    g = new_game()
    g.occupy(3, "attacker")            # 攻击方占领格（未激活，不计分）
    for cid in (6, 7, 8, 1, 2):
        g.occupy(cid, "defender")
    assert g.cells[3].owner == "attacker"
    g.occupy(5, "defender")            # 完成合围 -> 整片（含攻击方格）变防守方
    assert g.cells[3].owner == "defender"
    assert g.cells[4].owner == "defender"
    assert g.attacker_score == 0.0
    # 防守方得分 = 6 个已占格 + 2 个转换格 = 8 * 10
    assert g.defender_score == 80.0


def test_enclosure_blocked_by_unoccupied_neighbor():
    g = new_game()
    for cid in (1, 6, 7):
        g.occupy(cid, "defender")
    # 区域 {3}：邻接 4 未占领 -> 不成立
    assert g.cells[3].owner is None


def test_enclosure_unactivated_attacker_merged_not_blocking():
    """攻击方未激活地块不阻断包围：并入区域，包围成立时一并被吃掉。"""
    g = new_game()
    g.occupy(4, "attacker")            # 未激活（无能源路径）
    for cid in (1, 6, 7, 2, 5, 8):
        g.occupy(cid, "defender")
    # 区域 {3,4}：3 未占领 + 4 攻击方未激活，边界 1/2/5/6/7/8 全防守方 -> 成立
    assert g.cells[3].owner == "defender"
    assert g.cells[4].owner == "defender"   # 未激活地块被吃掉


def test_enclosure_blocked_by_activated_attacker():
    """攻击方激活地块在边界上 -> 包围无法成立（用户强调的核心边界）。"""
    g = new_game()
    g.occupy(7, "attacker")
    g.occupy(11, "attacker")
    g.occupy(16, "attacker")           # 7-11-16-22 能源路径 -> 7 激活
    assert g.cells[7].activated
    for cid in (1, 4, 6):
        g.occupy(cid, "defender")
    # 区域 {3}：边界 1/4/6 防守方 + 7 攻击方激活 -> 阻断
    assert g.cells[3].owner is None
    assert g.cells[7].owner == "attacker"


def test_enclosure_blocked_by_energy():
    g = new_game()
    for cid in (10, 11, 15, 17):
        g.occupy(cid, "defender")
    # 区域 {16}：邻接能源 22（非防守方）-> 不成立
    assert g.cells[16].owner is None


def test_enclosure_l1_in_region_but_not_converted():
    """L1 属于连通区域（参与区域判定），但包围转换时 L1 本身不被占领。"""
    g = new_game()
    for cid in (2, 3, 4):
        g.occupy(cid, "defender")
    # 区域 {0,1}：边界 2/3/4 全防守方 -> 成立；1 转换，L1（id 0）豁免保留
    assert g.cells[1].owner == "defender"
    assert g.cells[0].owner is None
    assert g.l1_high_score is None


def test_enclosure_l1_attacker_held_not_converted():
    """攻击方持有 L1 时，区域被围 -> 其余格转换，L1 仍归攻击方。"""
    g = new_game()
    g.occupy(0, "attacker", score=900000)
    for cid in (2, 3, 4):
        g.occupy(cid, "defender")
    # 区域 {0,1}：1 转换，L1 豁免
    assert g.cells[1].owner == "defender"
    assert g.cells[0].owner == "attacker"
    assert g.l1_high_team == "attacker"


def test_enclosure_sealed_by_defender_held_l1_and_map_edge():
    g = new_game()
    g.occupy(0, "defender", score=100)  # 防守方持有 L1
    for cid in (2, 3, 4):
        g.occupy(cid, "defender")
    # 区域 {1}：邻接 0/2/3/4 全防守方 + 地图边界（缺邻接槽）-> 成立
    assert g.cells[1].owner == "defender"
    # L1 本身豁免：不被包围转换（仍是防守方挑战持有，符合预期）


def test_enclosure_multiple_triggers_across_actions():
    g = new_game()
    # 第一次包围：L3 两侧被 L2+L4 围住
    for cid in (6, 7, 8, 9, 1, 2):
        g.occupy(cid, "defender")
    g.occupy(4, "defender")
    assert g.cells[3].owner == "defender"
    assert g.cells[5].owner == "defender"
    # 第二次包围（可多次触发）：L5 整行被 L4 + L6 围住，自动转换
    for cid in (15, 16, 17, 18, 19, 20):
        g.occupy(cid, "defender")
    assert g.cells[10].owner == "defender"
    assert g.cells[14].owner == "defender"


def test_energy_adjacent_attacker_never_captured():
    """区域含能源格/能源邻接的攻击方格不会被转换：邻接能源即阻断包围。"""
    g = new_game()
    g.occupy(15, "attacker")
    g.occupy(16, "attacker")
    for cid in (10, 11, 17):
        g.occupy(cid, "defender")
    # 区域 {15,16} 邻接能源 21/22 -> 不成立，攻击方格保留
    assert g.cells[15].owner == "attacker"
    assert g.cells[16].owner == "attacker"
    assert g.attacker_score == 22.0


# ---------------------------------------------------------------- 胜利


def test_top_victory():
    g = new_game()
    for cid in (15, 10, 6, 3, 1):    # 建立 能源21-15-10-6-3-1-L1 通路
        g.occupy(cid, "attacker")
    assert g.cells[1].activated
    g.occupy(0, "attacker", score=900000)  # 占领并激活 L1 -> 顶端直胜
    assert g.game_over
    assert g.winner == "attacker"
    assert g.win_type == "top"
    # 防守方分数保留（未吞噬）
    assert g.defender_score == 0.0


def test_timeout_winner_by_score():
    g = new_game()
    g.occupy(3, "defender")          # 10
    g.occupy(15, "attacker")         # 10
    g.occupy(16, "attacker")         # +11 -> 21
    g.end_game()
    assert g.game_over
    assert g.winner == "attacker"
    assert g.win_type == "timeout"


def test_timeout_draw():
    g = new_game()
    g.occupy(3, "defender")
    g.occupy(15, "attacker")
    g.end_game()
    assert g.winner == "draw"


def test_check_timeout_triggers_end():
    g = new_game()
    g.occupy(3, "defender")
    g.time_limit_minutes = 0.0   # 占领后再设 0，避免开局即超时
    assert g._check_timeout()
    assert g.game_over
    assert g.winner == "defender"  # 10 : 0


# ---------------------------------------------------------------- 更新链 / 状态


def test_update_chain_runs_on_every_occupation():
    """任何占领变化都触发 激活->包围->计分->直胜 链（顺序不可变）。"""
    g = new_game()
    g.occupy(15, "attacker")
    assert g.cells[15].activated
    assert g.attacker_score == 10.0
    # 攻击方建立通路后占 L1 -> 直胜在包围之后检查
    for cid in (10, 6, 3, 1):
        g.occupy(cid, "attacker")
    g.occupy(0, "attacker", score=999999)
    assert g.game_over and g.win_type == "top"


def test_state_dict_has_no_legacy_encirclement_fields():
    g = new_game()
    g.occupy(3, "defender")
    s = g.to_state_dict()
    assert "encircled" not in s
    assert "encirclement_active" not in s
    assert s["board"][3]["owner"] == "defender"
