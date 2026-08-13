"""无歌曲库回退任务生成测试。

运行：cd demo && python -m pytest tests/test_task_gen.py -q
"""

from controller.task_gen import TASK_TABLE, generate_tasks


def test_task_table_from_rules():
    assert len(TASK_TABLE) == 16
    assert TASK_TABLE[0]["name"] == "达成MM"
    assert TASK_TABLE[0]["weight"] == 2
    assert TASK_TABLE[0]["task_bonus"] == 10


def test_generate_tasks_shape():
    cells = generate_tasks(42)
    assert len(cells) == 21
    assert {c["id"] for c in cells} == set(range(21))
    l1 = cells[0]
    assert l1["task_bonus"] == 10
    assert l1["task_name"] == "L1源头 (固定+10)"


def test_generate_tasks_single_top_tier():
    """回退生成保证一局仅一首顶分（10 分制 tier=8，diff_score=10）。"""
    for seed in range(1, 11):
        cells = generate_tasks(seed)
        top = [c for c in cells if c["diff_score"] == 10]
        assert len(top) == 1, seed


def test_generate_tasks_reproducible():
    assert generate_tasks(5) == generate_tasks(5)
