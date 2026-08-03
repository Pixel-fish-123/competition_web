# 萌新杯音游比赛平台 — 生产镜像（多阶段构建）
#
# 构建上下文必须是仓库根目录（同时需要 frontend/ 与 backend/）：
#   docker build -f deploy/Dockerfile -t competition-web .
#
# 阶段 1：用 Node 构建前端产物（frontend/dist）
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# 阶段 2：Python 运行时，托管后端 + 前端静态产物
FROM python:3.14-slim

WORKDIR /app/backend

# 先装依赖（利用层缓存）
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝后端源码
COPY backend/ ./

# 从阶段 1 拷贝前端构建产物到 main.py 期望的仓库根 frontend/dist
# main.py 通过 3 次 os.path.dirname(__file__) 从 backend/app/main.py 解析到
# 仓库根，再拼接 "frontend"/"dist"，即 /app/frontend/dist。
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

EXPOSE 8000

# 生产环境变量（可在 docker-compose / 运行时覆盖）
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
