# ============================================================
# AI 漫剧 Autopilot v4 — Production image
# Multi-arch (amd64 + arm64) for Volcengine VKE / VeFaaS
# ============================================================

ARG PYTHON_IMAGE=python:3.11-slim-bookworm
FROM ${PYTHON_IMAGE} AS builder

ARG MANHUAJU_VERSION=0.4.0
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Build deps: ffmpeg, fonts (思源宋体 / 思源黑体), build-essential for native wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        fonts-noto-cjk \
        fonts-noto-cjk-extra \
        libgl1 \
        libglib2.0-0 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY scripts ./scripts
COPY web ./web

# Install with live + observability + db extras
RUN pip install --upgrade pip \
 && pip install --no-cache-dir ".[live,observe,db]"

# ============================================================
# Runtime stage — lean
# ============================================================
FROM ${PYTHON_IMAGE} AS runtime

ARG MANHUAJU_VERSION=0.4.0
LABEL org.opencontainers.image.title="manhuaju-autopilot" \
      org.opencontainers.image.version="${MANHUAJU_VERSION}" \
      org.opencontainers.image.source="https://github.com/manhuaju/autopilot" \
      org.opencontainers.image.description="AI 漫剧 Autopilot v4 — 小云雀 Agent 2.0 fast-path"

ENV PYTHONPATH=/app/src \
    MANHUAJU_API_DATA=/data \
    MANHUAJU_ENV=prod \
    PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OTEL_SERVICE_NAME=manhuaju-api \
    # VeFaaS 容器函数运行时兼容：函数平台会注入 _FC_SERVER_PORT 强制覆盖
    _FC_SERVER_PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
        fonts-noto-cjk-extra \
        libgl1 \
        libglib2.0-0 \
        curl \
        tini \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -ms /bin/bash manhuaju \
    && mkdir -p /data /app/_models \
    && chown -R manhuaju:manhuaju /data /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=builder /usr/local/bin/manhuaju* /usr/local/bin/
COPY --chown=manhuaju:manhuaju pyproject.toml README.md ./
COPY --chown=manhuaju:manhuaju src ./src
COPY --chown=manhuaju:manhuaju config ./config
COPY --chown=manhuaju:manhuaju web ./web
COPY --chown=manhuaju:manhuaju scripts ./scripts

USER manhuaju

VOLUME ["/data", "/app/_models"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl --fail --silent --max-time 5 http://127.0.0.1:8080/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# 端口由 $PORT / $_FC_SERVER_PORT 决定（VeFaaS 会覆写）。本地/ECS/K8s 不传时默认 8080。
CMD ["sh", "-c", "uvicorn manhuaju.api.app:app --host 0.0.0.0 --port ${_FC_SERVER_PORT:-${PORT:-8080}} --workers ${UVICORN_WORKERS:-2}"]
