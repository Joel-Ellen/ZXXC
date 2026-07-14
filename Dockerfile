# syntax=docker/dockerfile:1

FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

ARG NPM_REGISTRY=https://registry.npmjs.org
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --registry="$NPM_REGISTRY"

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


FROM python:3.11-slim AS python-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
WORKDIR /build

COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


FROM python:3.11-slim AS runtime

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/eduagent \
    XDG_CACHE_HOME=/app/cache \
    XDG_CONFIG_HOME=/app/cache/config \
    HF_HOME=/app/cache/huggingface \
    TORCH_HOME=/app/cache/torch \
    TMPDIR=/tmp

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 eduagent \
    && useradd --system --uid 10001 --gid 10001 --create-home --home-dir /home/eduagent eduagent \
    && mkdir -p /app/frontend /app/data /app/cache /app/logs /app/backups \
    && chown -R 10001:10001 /app /home/eduagent

WORKDIR /app

COPY --from=python-builder /opt/venv /opt/venv
COPY --chown=10001:10001 src/ ./src/
COPY --from=frontend-builder --chown=10001:10001 /app/frontend/dist/ ./frontend/dist/
COPY --chown=10001:10001 frontend/server.py ./frontend/server.py

USER 10001:10001

EXPOSE 8800

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8800/api/ready', timeout=4)" || exit 1

CMD ["python", "frontend/server.py"]
