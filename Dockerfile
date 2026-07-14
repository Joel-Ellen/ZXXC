# ============================================================================
# EduAgent Dockerfile — 多阶段构建
# ============================================================================
# 阶段 1: 构建 Vue 3 前端
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# 安装依赖
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --registry=https://registry.npmmirror.com

# 复制前端源码并构建
COPY frontend/index.html ./
COPY frontend/vite.config.js ./
COPY frontend/postcss.config.js ./
COPY frontend/tailwind.config.js ./
COPY frontend/src/ ./src/
COPY frontend/public/ ./public/
ARG VITE_SENTRY_DSN=
ARG VITE_SENTRY_ENVIRONMENT=production
ARG VITE_SENTRY_RELEASE=
ARG VITE_SENTRY_TRACES_SAMPLE_RATE=0.05
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN} \
    VITE_SENTRY_ENVIRONMENT=${VITE_SENTRY_ENVIRONMENT} \
    VITE_SENTRY_RELEASE=${VITE_SENTRY_RELEASE} \
    VITE_SENTRY_TRACES_SAMPLE_RATE=${VITE_SENTRY_TRACES_SAMPLE_RATE}
RUN npm run build

# ============================================================================
# 阶段 2: Python 后端运行环境
FROM python:3.11-slim

# 安装系统依赖 (argon2-cffi 需要 C 编译器，sentence-transformers 需要一些库)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 设置 pip 镜像源加速
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 先安装 Python 依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY src/ ./src/
COPY tests/ ./tests/
COPY scripts/ ./scripts/

# 复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist/ ./frontend/dist/

# 复制服务器入口文件
COPY frontend/server.py ./frontend/server.py

# 暴露端口
EXPOSE 8800

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8800/api/health')" || exit 1

# 启动服务
CMD ["python", "frontend/server.py"]
