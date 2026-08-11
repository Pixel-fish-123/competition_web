#!/usr/bin/env python3
"""GitHub push webhook 自动部署监听器（零第三方依赖，Python 3 标准库）。

- 监听 127.0.0.1:9000（由 Caddy 以 /deploy-webhook 路径反代出去，走 HTTPS）
- 校验 X-Hub-Signature-256（HMAC-SHA256，密钥来自环境变量 WEBHOOK_SECRET）
- 仅处理 refs/heads/main 的 push，触发 deploy/auto_deploy.sh
- 文件锁防止并发部署

环境变量：
  WEBHOOK_SECRET  与 GitHub Webhook 的 Secret 一致（必填）
  WEBHOOK_PORT    监听端口（默认 9000）
  REPO_DIR        仓库目录（默认 /opt/competition_web）
"""

import hashlib
import hmac
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
REPO_DIR = os.environ.get("REPO_DIR", "/opt/competition_web")
DEPLOY_SCRIPT = os.path.join(REPO_DIR, "deploy", "auto_deploy.sh")
PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))

_deploy_lock = threading.Lock()


def _verify_signature(body: bytes, signature_header: str | None) -> bool:
    """校验 GitHub X-Hub-Signature-256（HMAC-SHA256）。"""
    if not WEBHOOK_SECRET:
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature_header or "", expected)


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/deploy-webhook":
            self._reply(404, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._reply(400, "bad content-length")
            return
        body = self.rfile.read(length)

        if not _verify_signature(body, self.headers.get("X-Hub-Signature-256")):
            self._reply(403, "bad signature")
            return

        try:
            event = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._reply(400, "bad json")
            return

        if event.get("ref") != "refs/heads/main":
            self._reply(200, "ignored (not main push)")
            return

        if not _deploy_lock.acquire(blocking=False):
            self._reply(409, "deploy already running")
            return
        try:
            code = subprocess.call([DEPLOY_SCRIPT], cwd=REPO_DIR)
            self._reply(200, "deploy ok" if code == 0 else f"deploy failed: {code}")
        finally:
            _deploy_lock.release()

    def _reply(self, code: int, msg: str) -> None:
        data = json.dumps({"ok": code == 200, "msg": msg}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # noqa: A002
        pass  # 静默访问日志；部署日志由 auto_deploy.sh 输出


if __name__ == "__main__":
    if not WEBHOOK_SECRET:
        print("[webhook] WEBHOOK_SECRET 未设置，拒绝启动", file=sys.stderr)
        raise SystemExit(1)
    print(f"[webhook] listening on 127.0.0.1:{PORT} (repo={REPO_DIR})")
    ThreadingHTTPServer(("127.0.0.1", PORT), WebhookHandler).serve_forever()
