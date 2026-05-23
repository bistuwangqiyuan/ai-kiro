# AI 漫剧 Autopilot v4 — Volcengine 云部署指南

## 部署架构 (生产推荐)

```
                            ┌────────────────────────────────────┐
   用户请求 ─→  CDN ─→ TLS (VKE Ingress + cert-manager)           │
                            │            │                       │
                            │            ▼                       │
                            │     ┌──────────────────────┐        │
                            │     │  manhuaju-api Pods   │ HPA: 3-20
                            │     │  (FastAPI · uvicorn) │        │
                            │     └────┬──────────┬──────┘        │
                            │          │          │               │
                            │   ┌──────▼───┐  ┌───▼────────────┐  │
                            │   │  Worker  │  │ PostgreSQL RDS │  │
                            │   │  Pods    │  │ (Volcengine)   │  │
                            │   │ HPA: 4-30│  └────────────────┘  │
                            │   └────┬─────┘                       │
                            │        │                             │
   外部 API 调用 ←─────┐    │   ┌────▼──────────┐                  │
                     │    │   │ TOS (对象存储) │  ←  参考图/成片      │
   - Anthropic       │    │   └────┬──────────┘                  │
   - 火山 Visual SDK  ├────┘        │                             │
   - 火山 Ark (Doubao) │           ▼  CDN (image.manhuaju.x.com) │
   - ElevenLabs       │       小云雀 Agent 2.0 拉取               │
   - fal.ai          │                                            │
   - DashScope       │                                            │
                     └──→  KMS / Secrets ←── ExternalSecrets       │
                                                                  │
                  Observability: VMP (Prometheus) + Loki + Tempo  │
                                                                  │
                            └────────────────────────────────────┘
```

## 一键流程（5 步）

### 1. 拉取代码 + 准备 .env

```bash
git clone <repo>
cd ai-kiro
cp .env.example .env
# 填入所有必填 ★ Key
python -m scripts.smoke_keys --strict       # 验通
```

### 2. 本地一键启（docker-compose）

```bash
docker compose up -d --build
curl http://localhost:8080/health           # 期望 fast_path_ready=true
open http://localhost:8080/                 # 控制台
```

### 3. 构建 + 推送到 VCR

```bash
# 登录火山镜像仓库
docker login cr-cn-beijing.volces.com -u <username> -p <password>

# Buildx 多架构
docker buildx create --use --name manhuajubuilder
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t cr-cn-beijing.volces.com/manhuaju/manhuaju-autopilot:0.4.0 \
  -t cr-cn-beijing.volces.com/manhuaju/manhuaju-autopilot:latest \
  --push .
```

### 4. 部署到 VKE

```bash
# 准备 secrets（不要直接提交！）
kubectl create namespace manhuaju
kubectl create secret generic manhuaju-secrets \
  --from-env-file=.env \
  --namespace manhuaju

# 准备 TLS（cert-manager 或手动）
kubectl create secret tls manhuaju-tls \
  --cert=fullchain.pem --key=privkey.pem \
  --namespace manhuaju

# Helm 安装
helm upgrade --install manhuaju ./deploy/helm/manhuaju \
  --namespace manhuaju \
  --set ingress.host=api.manhuaju.example.com \
  --set image.tag=0.4.0 \
  --wait

# 检查
kubectl -n manhuaju get pods
curl -sk https://api.manhuaju.example.com/health | jq
```

### 5. 验收

```bash
# 1) /health 返回 fast_path_ready=true 且 system_mode=live
curl -sk https://api.manhuaju.example.com/health | jq .system_mode

# 2) 一键创建 3 集项目
curl -sk -X POST https://api.manhuaju.example.com/v1/projects \
  -H 'Content-Type: application/json' \
  -d '{
    "novel_text": "她从未想过，重生之后第一个见到的，竟是那个她以为已经死了的男人……",
    "episode_count": 3,
    "genre": "ancient",
    "episode_duration_s": 75,
    "platforms": ["douyin", "kuaishou", "weixin"]
  }' | jq

# 3) 查询进度
curl -sk https://api.manhuaju.example.com/v1/projects/$PROJECT_ID | jq
```

## VeFaaS 备选（无服务器，按调用计费）

若不想跑 VKE，可把 API 直接发到 VeFaaS：

```bash
# 1) 构建 VeFaaS-friendly zip（必要时去掉本地 ffmpeg）
zip -r vefaas.zip src config web pyproject.toml README.md \
  -x '*.pyc' -x '__pycache__/*'

# 2) 通过火山控制台或 vefaascli 部署：
vefaascli function create \
  --name manhuaju-api \
  --runtime python3.11 \
  --handler manhuaju.api.app:app \
  --memory 4096 \
  --timeout 900 \
  --code vefaas.zip
```

> ⚠️ VeFaaS 单次执行 ≤ 15 分钟；适合 API 层。视频渲染 worker 仍建议跑 VKE。

## TOS + CDN

1. 创建 TOS bucket：`manhuaju-assets`（华北-北京 1）。
2. 绑定 CDN 加速域名：`image.manhuaju.example.com`。
3. 设置 CORS：允许 `https://api.manhuaju.example.com`。
4. 把 CDN 域名填进 `.env`：`VOLCENGINE_TOS_CDN_DOMAIN=image.manhuaju.example.com`。

## RDS PostgreSQL

```sql
CREATE DATABASE manhuaju;
CREATE USER manhuaju WITH PASSWORD '<change-me>';
GRANT ALL PRIVILEGES ON DATABASE manhuaju TO manhuaju;
```

在 .env 写：

```
POSTGRES_DSN=postgresql://manhuaju:<pass>@<rds-host>:5432/manhuaju
```

## 可观测性

- **指标**：Prometheus annotations 已开。VMP 自动抓取 `/metrics`（启用 `observability.otel.enabled=true`）。
- **日志**：Loki Agent 收集 stdout（结构化 JSON）。
- **追踪**：OpenTelemetry → Tempo。设置：

```bash
helm upgrade ... \
  --set observability.otel.enabled=true \
  --set observability.otel.endpoint=http://vmp-collector.observability:4317
```

## 回滚

```bash
helm history manhuaju -n manhuaju
helm rollback manhuaju <REVISION> -n manhuaju
```

## 灰度

```bash
# 仅升级 API，不升级 worker（避免渲染中断）
helm upgrade manhuaju ./deploy/helm/manhuaju \
  --set worker.enabled=false \
  --set image.tag=0.4.1-rc1 \
  --namespace manhuaju
```

## 故障排查

| 现象 | 处理 |
|------|------|
| `/health` 报 `fast_path_ready=false` | 检查 manhuaju-secrets 是否齐备；`kubectl logs deploy/manhuaju-api` 看 provider 初始化错误 |
| 小云雀任务卡 `pending` 超过 30 分钟 | 看 `volcengine_xiaoyunque` 日志；切换 `MANHUAJU_VIDEO_PRIMARY=dashscope_wanx` 兜底 |
| 参考图 403/404 | TOS bucket 权限 / 预签名 TTL；CDN 缓存刷新 |
| 跨集 ArcFace < 0.92 | `insightface` 模型是否挂载到 `/opt/insightface/models`；reference_images 是否齐备 |
| 字层乱码 | 检查 fonts-noto-cjk 是否安装；`/v1/kpi.thresholds.garbled_text_rate_max=0` 是否启用了 ASS |
