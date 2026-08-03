"""可复用数据库重置脚本（todo 1）：完全重置、无备份、CLI 带确认/--yes 跳过。

删除整个 SQLite 数据库文件（competition.db 及其 -wal/-shm 伴生文件），
从 ``Base.metadata`` 重建全部表，并重新灌入种子数据（复用 seed.py 的
``seed_all``）。

流程（顺序敏感）：
1. 打印开发密码警告（复用 seed.py 的 ``_DEV_PASSWORD_WARNING``）与将要
   删除的数据库提示；
2. ``confirm=True`` 时等待回车确认（EOFError/非交互环境自动视为确认），
   ``--yes`` 跳过确认；
3. ``engine.dispose()`` 先关闭本进程全部连接，释放文件句柄；
4. 解析 ``settings.DB_PATH`` 为绝对路径，删除数据库及 -wal/-shm 伴生文件：
   ``Path.unlink`` 用 try/except PermissionError 包裹（正常缺失用
   missing_ok=True 忽略）。**锁检测必须前置**：WAL 模式下其他进程（如
   uvicorn）持有文件时，删除必然触发 PermissionError —— 这是真正的占用
   检测点；若在 unlink 之前调 drop_all，其他进程持有 BEGIN EXCLUSIVE 时会
   先抛 sqlite3.OperationalError（busy timeout），而非友好提示；
5. ``Base.metadata.create_all`` 重建全部表（删除文件已清空所有数据，
   drop_all 冗余故省略）；
6. 调用 ``seed_all`` 灌入种子数据；
7. 打印 seed_all 返回的摘要。

文件顶部 import 全部 ORM 模型（镜像 app/main.py:14-20）：否则
``Base.metadata`` 只认识 seed.py 间接 import 的 5 张表（User/Competition/
Registration/Team/TeamMember），Match/GameSession/PointTransaction/AuditLog
会被静默遗漏，导致"完全重置"静默失效。

用法（在 backend/ 目录下）::

    .venv\\Scripts\\python reset_db.py           # 回车确认后执行
    .venv\\Scripts\\python reset_db.py --yes     # 跳过确认直接执行

也可作为函数调用::

    from reset_db import reset_db
    summary = reset_db(confirm=False)  # 返回 seed_all 的摘要 dict
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Import the ORM models so Base.metadata knows about EVERY table for
# create_all (mirrors app/main.py:14-20). Without these, Match / GameSession /
# PointTransaction / AuditLog tables would silently stay missing after reset.
import app.models.audit_log  # noqa: F401
import app.models.competition  # noqa: F401
import app.models.match  # noqa: F401
import app.models.point  # noqa: F401
import app.models.registration  # noqa: F401
import app.models.team  # noqa: F401
import app.models.user  # noqa: F401

from app.config import settings
from app.db import Base, engine
from seed import _DEV_PASSWORD_WARNING, seed_all

# SQLite WAL 模式伴生文件后缀（-wal 日志、-shm 共享内存索引）。
_SIDECAR_SUFFIXES = ("", "-wal", "-shm")

_DB_LOCKED_HINT = "数据库被占用，请先停止后端服务（uvicorn）后重试"


def reset_db(confirm: bool = True) -> dict:
    """完全重置数据库：删文件 → 重建表 → 重灌种子数据。

    :param confirm: True 时等待回车确认（EOFError/非交互环境自动视为确认）。
    :returns: seed_all() 返回的摘要 dict（如 {"skipped": False, "users": 10, ...}）。
    """
    db_path = Path(settings.DB_PATH).resolve()
    print(_DEV_PASSWORD_WARNING)
    print("将删除 backend/competition.db 并重建种子数据")
    print(f"目标数据库: {db_path}")

    if confirm:
        try:
            input("按 Enter 继续，Ctrl+C 取消...")
        except EOFError:
            # 非交互环境（管道/脚本重定向）无 stdin 输入，视为已确认。
            pass

    # 先关闭本进程全部连接（含连接池中的），释放对数据库文件的句柄。
    engine.dispose()

    # 锁检测：删除数据库文件及伴生文件。其他进程持有文件时 unlink 必然
    # PermissionError，在此捕获并给出友好提示，而不是让后续 create_all/seed
    # 抛裸 sqlite3.OperationalError。必须在任何破坏性操作之前执行。
    for suffix in _SIDECAR_SUFFIXES:
        target = db_path.with_name(db_path.name + suffix)
        try:
            target.unlink(missing_ok=True)
        except PermissionError:
            print(_DB_LOCKED_HINT)
            sys.exit(1)

    # 删除文件已清空所有数据，直接重建全部表（drop_all 冗余，不调用）。
    Base.metadata.create_all(bind=engine)

    # 重灌种子数据（fresh 库必然执行，非 skipped）。
    summary = seed_all()
    print(f"重置完成，seed 摘要: {summary}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="完全重置数据库（删除文件 + 重建表 + 重灌种子数据，无备份）"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="跳过回车确认直接执行",
    )
    args = parser.parse_args()
    reset_db(confirm=not args.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
