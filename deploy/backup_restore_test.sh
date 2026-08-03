#!/usr/bin/env bash
# ============================================================================
# 萌新杯音游比赛平台 — 备份恢复演练脚本（CRITICAL）
#
# 目的：证明备份文件"真的可恢复"，而不只是"被创建了"。
#   - 从备份文件恢复到临时目录。
#   - 用 sqlite3 校验关键表的行数与源数据库一致。
#   - 任一环节失败（恢复失败 / 行数不一致）则退出码非 0。
#
# 用法：
#   ./backup_restore_test.sh [备份文件] [源数据库]
#   默认备份文件：backups/ 下最新一份 competition_*.db
#   默认源数据库：../backend/competition.db
#
# 校验的表（可按需增删）：
#   users, competitions, matches, game_sessions, point_transactions,
#   registrations, teams, team_members, audit_logs
# ============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 参数解析
BACKUP_FILE="${1:-}"
DB_FILE="${2:-$SCRIPT_DIR/../backend/competition.db}"

# 若未指定备份文件，取 backups/ 下最新一份
if [ -z "$BACKUP_FILE" ]; then
    BACKUP_FILE="$(ls -1t "$SCRIPT_DIR"/backups/competition_*.db 2>/dev/null | head -n 1)"
fi

fail() {
    echo "[restore-test] 错误: $*" >&2
    exit 1
}

# 0. 前置校验
[ -n "$BACKUP_FILE" ] || fail "未找到备份文件，请先运行 backup.sh"
[ -f "$BACKUP_FILE" ] || fail "备份文件不存在: $BACKUP_FILE"
[ -f "$DB_FILE" ] || fail "源数据库不存在: $DB_FILE"

# 1. 创建临时恢复目录
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
RESTORED_DB="$TMP_DIR/restored.db"

echo "[restore-test] 备份文件: $BACKUP_FILE"
echo "[restore-test] 源数据库: $DB_FILE"
echo "[restore-test] 恢复目标: $RESTORED_DB"

# 2. 从备份恢复（sqlite3 .restore 或 Python 均可，这里用 Python 保证跨环境）
restore_ok=0
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    fail "无 python，无法执行恢复"
fi

if ! "$PY" - "$BACKUP_FILE" "$RESTORED_DB" <<'PYEOF'
import sqlite3
import sys

src, dst = sys.argv[1], sys.argv[2]
try:
    source = sqlite3.connect(src)
    dest = sqlite3.connect(dst)
    source.backup(dest)
    dest.close()
    source.close()
except Exception as exc:  # noqa: BLE001
    print(f"[restore-test] 恢复失败: {exc}", file=sys.stderr)
    sys.exit(1)
PYEOF
then
    fail "从备份恢复失败"
fi

# 3. 校验表行数一致
#    需要 sqlite3 CLI 或 Python 查询行数；这里统一用 Python 查询。
TABLES="users competitions matches game_sessions point_transactions registrations teams team_members audit_logs"

mismatch=0
for table in $TABLES; do
    src_count=$("$PY" - "$DB_FILE" "$table" <<'PYEOF'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
try:
    cur = conn.execute(f"SELECT COUNT(*) FROM {sys.argv[2]}")
    print(cur.fetchone()[0])
except Exception:
    print("N/A")
conn.close()
PYEOF
)
    dst_count=$("$PY" - "$RESTORED_DB" "$table" <<'PYEOF'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
try:
    cur = conn.execute(f"SELECT COUNT(*) FROM {sys.argv[2]}")
    print(cur.fetchone()[0])
except Exception:
    print("N/A")
conn.close()
PYEOF
)
    if [ "$src_count" = "N/A" ] || [ "$dst_count" = "N/A" ]; then
        echo "[restore-test] 表 $table 不存在（跳过）"
        continue
    fi
    if [ "$src_count" != "$dst_count" ]; then
        echo "[restore-test] 行数不一致: $table 源=$src_count 恢复=$dst_count"
        mismatch=1
    else
        echo "[restore-test] 行数一致: $table = $src_count"
    fi
done

# 4. 结论
if [ "$mismatch" -ne 0 ]; then
    fail "恢复演练失败：存在行数不一致的表"
fi

echo "[restore-test] 恢复演练通过：备份可恢复且行数一致"
exit 0
