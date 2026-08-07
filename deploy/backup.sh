#!/usr/bin/env bash
# ============================================================================
# 萌新杯音游比赛平台 — SQLite 在线备份脚本（cron 友好）
#
# 功能：
#   - 使用 sqlite3 的 .backup 命令做安全在线备份（WAL 模式下也正确，
#     会一并捕获 -wal/-shm 中尚未 checkpoint 的数据，无需停服）。
#   - 若系统无 sqlite3 CLI，自动回退到 Python 的 sqlite3 模块做备份。
#   - 备份文件写入 ./backups/ 目录，文件名带时间戳。
#   - 仅保留最近 7 份备份，更早的自动删除。
#   - 成功退出码 0，失败退出码非 0。
#
# 用法：
#   ./backup.sh [数据库路径] [备份目录]
#   默认数据库路径：../data/competition.db（相对本脚本所在目录）
#   默认备份目录：  ./backups（相对本脚本所在目录）
#
# cron 示例（每天凌晨 3 点）：
#   0 3 * * * /path/to/deploy/backup.sh >> /var/log/competition-backup.log 2>&1
# ============================================================================

set -u

# 定位脚本所在目录（兼容软链接）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 参数解析
DB_FILE="${1:-$SCRIPT_DIR/../data/competition.db}"
BACKUP_DIR="${2:-$SCRIPT_DIR/backups}"

# 时间戳：YYYYMMDD_HHMMSS
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/competition_${TIMESTAMP}.db"

# 保留份数
KEEP=7

fail() {
    echo "[backup] 错误: $*" >&2
    exit 1
}

# 0. 校验数据库文件存在
if [ ! -f "$DB_FILE" ]; then
    fail "数据库文件不存在: $DB_FILE"
fi

# 1. 创建备份目录
mkdir -p "$BACKUP_DIR" || fail "无法创建备份目录: $BACKUP_DIR"

# 2. 执行备份
backup_ok=0
if command -v sqlite3 >/dev/null 2>&1; then
    # 首选：sqlite3 CLI 的 .backup 命令（在线安全备份，正确处理 WAL）
    if sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"; then
        backup_ok=1
    else
        echo "[backup] sqlite3 .backup 失败，尝试 Python 回退" >&2
    fi
fi

if [ "$backup_ok" -eq 0 ]; then
    # 回退：Python sqlite3 模块（backup API 同样正确处理 WAL）
    if command -v python3 >/dev/null 2>&1; then
        PY=python3
    elif command -v python >/dev/null 2>&1; then
        PY=python
    else
        fail "既无 sqlite3 CLI 也无 python，无法备份"
    fi

    if ! "$PY" - "$DB_FILE" "$BACKUP_FILE" <<'PYEOF'
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
    print(f"[backup] Python 备份失败: {exc}", file=sys.stderr)
    sys.exit(1)
PYEOF
    then
        fail "备份失败: $DB_FILE"
    fi
    backup_ok=1
fi

# 3. 校验备份文件非空且可读
if [ ! -s "$BACKUP_FILE" ]; then
    fail "备份文件为空或不存在: $BACKUP_FILE"
fi

# 4. 清理旧备份，仅保留最近 KEEP 份
#    （按文件名时间戳排序，保留最新的 KEEP 个）
ls -1 "$BACKUP_DIR"/competition_*.db 2>/dev/null \
    | sort -r \
    | tail -n +$((KEEP + 1)) \
    | while read -r old; do
        rm -f "$old" && echo "[backup] 删除旧备份: $old"
    done

echo "[backup] 备份成功: $BACKUP_FILE"
exit 0
