#!/usr/bin/env bash
# 自动部署脚本（webhook 触发）：拉取 main 最新代码并重建容器。
# 由 deploy/webhook_listener.py 调用；日志输出到 stdout（systemd journal）。
set -u

REPO_DIR="$(cd "$(dirname "$(dirname "$(readlink -f "$0")")")" && pwd)"
cd "$REPO_DIR" || exit 1

echo "[deploy $(date '+%F %T')] start: $REPO_DIR"

# 1. 拉取最新代码。
#    服务器上 deploy/docker-compose.yml 通常有本地生产配置（密钥/端口），
#    pull 遇到该文件冲突时先暂存、拉取、再恢复。
if ! git pull --ff-only; then
    echo "[deploy] pull 失败，尝试暂存 compose 后重试"
    git stash push -m "auto-deploy compose" deploy/docker-compose.yml || exit 1
    if ! git pull --ff-only; then
        echo "[deploy] git pull 仍然失败，中止"
        exit 1
    fi
    git stash pop || echo "[deploy] 警告：stash pop 失败，请手动检查 compose"
fi

# 2. 确认生产配置仍在（防止 stash pop 冲突后丢失）。
grep -q "127.0.0.1:8000:8000" deploy/docker-compose.yml || echo "[deploy] 警告：8000 端口绑定与预期不符"
grep -q 'AUTH_COOKIE_SECURE: "true"' deploy/docker-compose.yml || echo "[deploy] 警告：AUTH_COOKIE_SECURE 与预期不符"

# 3. 重建并启动。
docker compose -f deploy/docker-compose.yml up -d --build
code=$?

# 4. 健康检查。
sleep 3
if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "[deploy] 健康检查通过"
else
    echo "[deploy] 警告：健康检查失败，请查看容器日志"
fi

echo "[deploy] done (exit=$code)"
exit $code
