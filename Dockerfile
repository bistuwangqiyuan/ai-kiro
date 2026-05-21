FROM python:3.11-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

FROM python:3.11-slim AS runtime

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config

ENV PYTHONPATH=src
ENV MANHUAJU_API_DATA=/data
VOLUME ["/data"]

EXPOSE 8080
CMD ["uvicorn", "manhuaju.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
