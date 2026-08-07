# 萌新杯音游比赛平台
# 阿里云香港 ECS 部署步骤

本文按 **阿里云香港 ECS + Ubuntu + Docker + Caddy HTTPS** 编写。

适合当前配置：

- 2 核 vCPU
- 2 GiB 内存
- 40 GiB 系统盘
- 香港地域

当前项目规模下，这个配置可以运行。建议额外配置 2 GiB Swap，避免首次构建前端时内存不足。

## 0. 部署架构

```text
用户浏览器
    ↓ HTTPS 443
Caddy
    ↓ HTTP 127.0.0.1:8000
Docker Compose app
    ├── FastAPI 后端
    ├── frontend/dist 前端静态文件
    └── /app/data/competition.db SQLite 数据库
```

香港节点通常不需要 ICP 备案，国内用户可以直接访问香港 ECS 上的域名或公网 IP。

正式环境建议使用域名和 HTTPS，不建议长期直接暴露 `8000` 端口。

## 1. 创建 ECS

在阿里云控制台创建或领取 ECS：

- 地域：香港
- 系统：Ubuntu 22.04/24.04 64 位
- 配置：2 核 2 GiB
- 系统盘：40 GiB
- 必须分配公网 IPv4

## 2. 配置安全组

安全组入方向至少放行：

| 协议 | 端口 | 来源 | 用途 |
| --- | --- | --- | --- |
| TCP | 22 | 仅你的公网 IP，或临时 `0.0.0.0/0` | SSH 管理 |
| TCP | 80 | `0.0.0.0/0` | HTTP/证书申请 |
| TCP | 443 | `0.0.0.0/0` | HTTPS 网站 |

正式部署不需要开放 `8000`。如果没有域名、只想临时测试，才临时开放 TCP `8000`。

## 3. SSH 登录服务器

Windows PowerShell 执行：

```powershell
ssh root@你的ECS公网IP
```

如果使用阿里云控制台提供的普通用户，把 `root` 替换成实际用户名。

确认系统：

```bash
cat /etc/os-release
```

应能看到 Ubuntu 信息。

## 4. 更新系统并安装基础工具

在 ECS SSH 终端执行：

```bash
apt update
apt upgrade -y
apt install -y git curl ca-certificates openssl
```

## 5. 配置 Swap

2 GiB 内存建议执行：

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile swap swap defaults 0 0' >> /etc/fstab
```

检查结果：

```bash
free -h
```

`Swap` 应显示约 `2.0G`。

## 6. 安装 Docker

执行：

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker --version
docker compose version
```

两个版本命令都能正常输出后再继续。

## 7. 获取项目代码

如果项目已经推送到 GitHub：

```bash
cd /opt
git clone https://github.com/Pixel-fish-123/competition_web.git
cd /opt/competition_web
```

如果仓库是私有仓库，使用 SSH Key 或其他 Git 认证方式克隆。

检查项目文件：

```bash
ls
ls deploy
```

应该能看到 `backend`、`frontend`、`deploy` 和 `deploy/docker-compose.yml`。

> 注意：本地未提交的修改不会出现在服务器的 `git clone` 中。部署前必须先提交并推送，或者将当前项目压缩上传到服务器。

## 8. 配置生产密钥

生成随机密钥：

```bash
openssl rand -hex 32
```

复制输出结果，然后编辑 compose 文件：

```bash
nano deploy/docker-compose.yml
```

找到：

```yaml
SECRET_KEY: "CHANGE_ME_TO_A_RANDOM_SECRET"
```

替换为随机密钥，例如：

```yaml
SECRET_KEY: "这里填写openssl生成的随机字符串"
```

不要把真实密钥公开提交到 GitHub。

确认 compose 中包含以下配置：

```yaml
DATABASE_URL: "sqlite:////app/data/competition.db"
DB_PATH: "/app/data/competition.db"
AUTH_COOKIE_SECURE: "true"
```

如果已经准备好域名和 HTTPS，把端口设置为仅本机访问：

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

## 9. 构建并启动 Docker 服务

执行：

```bash
cd /opt/competition_web
docker compose -f deploy/docker-compose.yml up -d --build
```

首次构建需要几分钟。

检查容器状态：

```bash
docker compose -f deploy/docker-compose.yml ps
```

`app` 应显示 `Up` 或 `running`。

查看日志：

```bash
docker compose -f deploy/docker-compose.yml logs --tail=100 app
```

如果看到 Uvicorn 启动并监听 `0.0.0.0:8000`，说明后端已经启动。

## 10. 初始化演示账号

生产环境如果不需要演示账号，可以跳过本节并自行注册第一个管理员账号。

需要开发演示数据时执行：

```bash
docker compose -f deploy/docker-compose.yml exec app python seed.py
```

默认账号仅用于初始化：

```text
管理员：admin / admin123
裁判：referee / referee123
选手：player1-8 / player123
```

首次登录后，必须修改或删除这些默认账号密码。

## 11. 配置域名解析

在域名 DNS 控制台添加：

| 类型 | 主机记录 | 记录值 |
| --- | --- | --- |
| A | `@` | ECS 公网 IPv4 |
| A | `www` | ECS 公网 IPv4，可选 |

等待 DNS 生效后，在服务器执行：

```bash
ping -c 2 your-domain.com
```

如果解析结果是 ECS 公网 IP，就可以继续配置 HTTPS。

## 12. 安装 Caddy

执行：

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install -y caddy
```

编辑 Caddy 配置：

```bash
nano /etc/caddy/Caddyfile
```

写入以下内容，替换域名和邮箱：

```caddy
    email your-email@example.com
    reverse_proxy 127.0.0.1:8000
}
```

检查并启动：

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl enable --now caddy
systemctl reload caddy
systemctl status caddy
```

Caddy 会自动申请 Let's Encrypt 证书，并自动续期。

## 13. 验证网站

服务器本机验证：

```bash
curl -I http://127.0.0.1:8000
curl -I https://your-domain.com
```

浏览器访问：

```text
https://your-domain.com
```

检查以下功能：

- 首页能正常打开
- 登录和注册正常
- 管理员能进入管理后台
- 对局页面能正常加载
- WebSocket 对局状态能实时更新
- 浏览器地址栏显示 HTTPS 锁标志

## 14. 无域名临时测试

如果暂时没有域名，可以临时使用公网 IP。

编辑 compose：

```bash
nano deploy/docker-compose.yml
```

把端口改为：

```yaml
ports:
  - "8000:8000"
```

在阿里云安全组开放 TCP `8000`，然后重启：

```bash
docker compose -f deploy/docker-compose.yml up -d
```

访问：

```text
http://ECS公网IP:8000
```

这只适合临时测试，不建议作为正式访问地址。

## 15. 更新网站

代码更新并推送到仓库后，在服务器执行：

```bash
cd /opt/competition_web
git pull
docker compose -f deploy/docker-compose.yml up -d --build
```

数据库位于 `deploy/data/competition.db`，重新构建容器不会删除数据库。

## 16. 备份数据库

项目使用 SQLite WAL，不能只随意复制一个正在运行的 `.db` 文件。

执行项目提供的安全备份脚本：

```bash
cd /opt/competition_web/deploy
chmod +x backup.sh
./backup.sh
```

备份文件会写入：

```text
/opt/competition_web/deploy/backups/
```

建议将备份同步到 ECS 之外的存储位置，例如 OSS 或本地电脑。

## 17. 常见问题

### Docker 构建时被杀掉

通常是内存不足。确认 Swap 已启用：

```bash
free -h
```

然后重试：

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

### 浏览器打不开网站

依次检查：

```bash
docker compose -f deploy/docker-compose.yml ps
systemctl status caddy
ss -lntp | grep -E ':80|:443|:8000'
```

同时检查阿里云安全组是否开放了 `80` 和 `443`。

### Caddy 无法申请证书

确认：

- 域名 A 记录已经指向 ECS 公网 IP
- 安全组开放 TCP `80` 和 `443`
- 域名拼写正确
- 没有其他服务占用 `80` 或 `443`

查看日志：

```bash
journalctl -u caddy -n 100 --no-pager
```

### 登录后立即掉线

确认 compose 中存在：

```yaml
AUTH_COOKIE_SECURE: "true"
```

并且用户访问的是 `https://`，不是 `http://`。

### 忘记生产密钥

重新生成并修改 compose 后重启：

```bash
docker compose -f deploy/docker-compose.yml up -d
```

修改密钥会使已有登录 Cookie 失效，用户需要重新登录。

## 18. 上线检查清单

- [ ] ECS 位于香港并有公网 IPv4
- [ ] 安全组开放 22、80、443
- [ ] 已配置 2 GiB Swap
- [ ] Docker 和 Docker Compose 安装成功
- [ ] 已替换 `SECRET_KEY`
- [ ] 已确认数据库挂载到 `deploy/data`
- [ ] 已执行 `docker compose up -d --build`
- [ ] 已初始化或创建管理员账号
- [ ] 默认账号密码已修改或删除
- [ ] 域名 A 记录已经指向 ECS IP
- [ ] Caddy HTTPS 证书申请成功
- [ ] 登录、后台、对局、WebSocket 已验证
- [ ] 已执行一次数据库备份
