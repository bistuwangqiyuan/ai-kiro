# ============================================================
# AI 漫剧 Autopilot v4 — Production image (slim)
# amd64 only for Volcengine VeFaaS / VKE
# Build-time goal: keep compressed image under 600MB for fast push to Beijing VCR
# ============================================================

ARG PYTHON_IMAGE=python:3.11-slim-bookworm
FROM ${PYTHON_IMAGE} AS builder

ARG MANHUAJU_VERSION=0.4.0
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY scripts ./scripts
COPY web ./web

# 仅安装 live extras：VeFaaS 主路径不强依赖 DB/观测；如启用 OTel/PG 用环境变量切换 (manhuaju[observe,db])。
# 关闭 wheel 缓存 + strip pip cache 减镜像 ~200MB。
RUN pip install --upgrade pip \
 && pip install --no-cache-dir ".[live]" \
 && find /usr/local/lib/python3.11/site-packages -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true \
 && find /usr/local/lib/python3.11/site-packages -name '*.pyc' -delete 2>/dev/null || true \
 && find /usr/local/lib/python3.11/site-packages -name 'tests' -type d -exec rm -rf {} + 2>/dev/null || true \
 && find /usr/local/lib/python3.11/site-packages -name 'test' -type d -exec rm -rf {} + 2>/dev/null || true

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
    _FC_SERVER_PORT=8080

WORKDIR /app

# 运行时只装 ffmpeg + 中文字体 + tini；不装 libgl/libglib（用不到 cv2 GUI）。
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
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
CMD ["sh", "-c", "uvicorn manhuaju.api.app:app --host 0.0.0.0 --port ${_FC_SERVER_PORT:-${PORT:-8080}} --workers ${UVICORN_WORKERS:-2}"]
