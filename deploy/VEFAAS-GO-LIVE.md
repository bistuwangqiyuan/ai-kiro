# 🚀 AI 漫剧 Autopilot v4 — 火山 VeFaaS 无服务器上线清单

> 目标：**零服务器、按调用计费、自动伸缩到 0**。
> 总耗时：**约 30 分钟**（开火山账号 + 容器服务 + 函数服务 + GitHub Secrets）。
> 总闲时月成本：**¥0**（VeFaaS 缩到 0 不计费；VCR 镜像存储 ~¥1/月）。
> 调用计费：每集生成约消耗 ~¥1.5 算力 + 视频 API 调用费（不在 VeFaaS 计费内）。

> **🟢 当前线上状态（2026-05-26）**：
> - 公网 URL：`https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com`
> - `/health` → 200，`/docs` → 200，`/openapi.json` → 200
> - 端到端验证：`POST /v1/projects` 真实跑通，生成 `ep01.mp4` + 抖音分发包，七维 QA 全部 ≥8.0
> - Worker 已并入 API：`POST /v1/internal/worker/tick`（被 VeFaaS Timer 每分钟触发），无独立 worker 函数
> - 函数：`manhuaju-api`（`ex9xkzt4`），4 GB / 2 CPU / max_concurrency=10
> - APIG：`gd8afjpepm94qqo1kmttg` → service `sd8ap3btqc6mqij6t2bsg` → route `manhuaju-root`（直接绑定 FunctionId）

---

## 🗺️ 部署架构图

```
                ┌────────────────────────────────────────┐
                │  GitHub  (你已经 push 了)              │
                │  └─ Actions: 自动 build → 推 VCR       │
                │     └─ 推完触发 VeFaaS 热更            │
                └──────────┬─────────────────────────────┘
                           │ image:sha
                           ▼
              ┌──────────────────────────────┐
              │ 火山 VCR（容器镜像仓库）     │
              │  manhuaju-autopilot:<sha>    │
              └──────┬───────────────────────┘
                     │ pull
            ┌────────┴────────┐
            ▼                 ▼
   ┌────────────────────────────────────────┐
   │  VeFaaS：manhuaju-api                  │
   │  - APIG HTTP 触发器（公网域名 + TLS）  │
   │  - VeFaaS Timer 触发 /internal/worker/tick │
   │  - 缩到 0                              │
   └────────────────┬───────────────────────┘
                    │ 文件读写
                    ▼
        ┌──────────────────────────────┐
        │ 火山 TOS（对象存储）         │
        │   manhuaju-prod 桶           │
        │   - 角色参考图               │
        │   - 渲染产物（mp4/jpg）      │
        └──────────────────────────────┘
```

---

## ✅ 前置已完成

- [x] 火山账号已实名
- [x] 3 个视觉应用已开通（小云雀 / Seedream / 即梦）
- [x] VOLCENGINE_VISUAL_AK/SK 已配
- [x] VOLCENGINE_ARK_API_KEY 已配
- [x] VOLCENGINE_TOS_AK/SK + Bucket 已配
- [x] 代码已 push 到 `bistuwangqiyuan/ai-kiro`

---

## 📋 后续 5 步（按顺序）

### 步骤 1 — 开通容器镜像服务 VCR（5 分钟）

1. 打开 **https://console.volcengine.com/cr**
2. 点 **"开通服务"**（如已开通跳过）
3. 左侧选 **"实例列表"** → 选默认实例 `enterprise-1` 或 `basic-1`（都可以，basic 免费）
4. 左侧 **"命名空间"** → **"创建命名空间"**
   - 名称：`manhuaju`（务必小写，全局唯一前缀）
   - 访问级别：**公开** 或 **私有**（推荐私有 → 配密码）
5. 左侧 **"镜像仓库"** → **"创建镜像仓库"**
   - 命名空间：`manhuaju`
   - 仓库名称：`manhuaju-autopilot`
   - 仓库类型：**私有**
6. 左侧 **"用户中心"** → **"设置密码"**（这个密码就是 GHA 用的 `VCR_PASSWORD`）
   - 用户名：你的火山账号 ID（控制台右上角 → 用户信息可看；形如 `2107xxxxxxxxxxxx`）

✅ **拿到 3 个东西**：
- `命名空间`: `manhuaju`（或你起的名字）
- `VCR_USERNAME`: 火山账号 ID
- `VCR_PASSWORD`: 刚才设的密码

---

### 步骤 2 — GitHub 配 Secrets / Variables（3 分钟）

打开 **https://github.com/bistuwangqiyuan/ai-kiro/settings/secrets/actions**

#### Repository Secrets（加密保存）

| Name | Value |
|---|---|
| `VCR_USERNAME` | 步骤 1 拿到的火山账号 ID |
| `VCR_PASSWORD` | 步骤 1 设的 VCR 密码 |
| `VOLCENGINE_AK` | `.env` 里的 `VOLCENGINE_VISUAL_AK`（同一对 AK） |
| `VOLCENGINE_SK` | `.env` 里的 `VOLCENGINE_VISUAL_SK`（同一对 SK） |

#### Repository Variables（明文）

打开 **Variables** 标签页 → **New repository variable**

| Name | Value |
|---|---|
| `VCR_NAMESPACE` | `manhuaju`（与步骤 1 一致） |

---

### 步骤 3 — 触发 GHA 首次 build（自动，~6 分钟）

回到本机 PowerShell：

```powershell
cd D:\project\cursor\dev\ai-kiro
git commit --allow-empty -m "ci: trigger first build for VeFaaS"
git push
```

打开 **https://github.com/bistuwangqiyuan/ai-kiro/actions** 看进度。

✅ 完成后，你会在 **https://console.volcengine.com/cr** → 镜像仓库 `manhuaju/manhuaju-autopilot` 里看到新镜像（tag 是 commit sha 短码 + `latest`）。

> 第一次 build 因为多架构（amd64+arm64）会慢一些（5-8 min），后续走缓存只要 2 min。

---

### 步骤 4 — 火山 VeFaaS 创建函数（10 分钟，控制台手工，仅这一次）

打开 **https://console.volcengine.com/vefaas**

> 如果没开通：点 **"立即开通"** → 同意条款，免费开通。

#### 4.1 创建 API 函数

1. **"函数管理"** → **"创建函数"**
2. **基础信息**：
   - 函数名称：`manhuaju-api`
   - 描述：`AI 漫剧 v4 — FastAPI HTTP 入口`
   - 运行时：**自定义运行时（容器镜像）** ← 一定要选这个
   - 来源：**镜像**
   - 镜像地址：`cr-cn-beijing.volces.com/manhuaju/manhuaju-autopilot:latest`
     - 如果 VCR 是私有的，会自动用账号 AK 拉，无需密码
   - 启动命令：**留空**（用 Dockerfile 默认 CMD）
   - 端口：**8080**
3. **资源配置**：
   - CPU：`2 核`
   - 内存：`4096 MB`
   - 实例并发：`10`
   - 单次超时：`1800 秒`（30 分钟）
4. **触发器**：
   - 选 **HTTP 触发器**
   - 鉴权方式：**无鉴权**（首次试用方便；正式上线建议 `SignatureAuth`）
   - 完成后页面会给你一个公网域名，形如：
     `https://manhuaju-api-xxxxx.cn-beijing.fcapp.run`
5. **环境变量**（这一步很重要！）：

| Key | Value |
|---|---|
| `MANHUAJU_LIVE_MODE` | `live` |
| `MANHUAJU_API_DATA` | `/data` |
| `UVICORN_WORKERS` | `2` |
| `VOLCENGINE_VISUAL_AK` | （你的） |
| `VOLCENGINE_VISUAL_SK` | （你的） |
| `VOLCENGINE_ARK_API_KEY` | （你的） |
| `VOLCENGINE_TOS_AK` | 同 VISUAL_AK |
| `VOLCENGINE_TOS_SK` | 同 VISUAL_SK |
| `VOLCENGINE_TOS_BUCKET` | `manhuaju-prod`（或你的桶名） |
| `VOLCENGINE_TOS_REGION` | `cn-beijing` |
| `VOLCENGINE_TOS_ENDPOINT` | `tos-cn-beijing.volces.com` |

   > 可选：`DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`、`GLM_API_KEY`、`MOONSHOT_API_KEY` —— 有就填，作为 LLM fallback。

6. **存储**（可选）：
   - 挂载 **NAS** 到 `/data`，让 SQLite 状态持久化（不挂的话每次冷启动数据清零，仅适合 stateless 调用）
   - 容量选 **100 GB**（按用量计费，~¥0.3/GB·月）
7. 点 **"创建"**。等 1-2 分钟，状态变绿色 `就绪`。
8. 点函数详情 → **"触发器"** 标签 → 复制 HTTP URL（这就是你的公网入口）

#### 4.2 创建 Worker 函数

1. **"函数管理"** → **"创建函数"**
2. **基础信息**：
   - 函数名称：`manhuaju-worker`
   - 描述：`AI 漫剧 v4 — 后台 worker`
   - 运行时：**自定义运行时（容器镜像）**
   - 镜像地址：`cr-cn-beijing.volces.com/manhuaju/manhuaju-autopilot:latest`
   - 启动命令：**`python -m scripts.run_worker_once`** ← 这里要覆盖 CMD
   - 端口：**留空**（不是 HTTP 函数）
3. **资源配置**：
   - CPU：`2 核`
   - 内存：`4096 MB`
   - 实例并发：`1`
   - 单次超时：`1800 秒`
4. **触发器**：
   - 选 **定时触发器**
   - Cron：`*/1 * * * *`（每分钟一次）
5. **环境变量**：和 API 函数一样，全复制一份（你也可以用 VeFaaS 的「配置组」功能共享）
6. **存储**：挂同一个 NAS 到 `/data`（让 worker 和 api 共享 batch.sqlite）
7. 点 **"创建"**。

---

### 步骤 5 — 验证上线（2 分钟）

```powershell
# 用步骤 4.1 拿到的公网 URL 替换下面这个
$URL = "https://manhuaju-api-xxxxx.cn-beijing.fcapp.run"

# 健康检查
curl "$URL/health"
# 期望返回：{"status":"ok",...}

# 看版本/能力
curl "$URL/v1/health"

# 打开 Web 控制台
Start-Process "$URL/console.html"

# 投一个项目（最小冒烟，1 集 50 秒短视频）
curl -X POST "$URL/v1/projects" -H "Content-Type: application/json" -d '{
  "title":"测试-上线冒烟",
  "novel_text":"夜雨连绵，林深听见门外的脚步。她握紧手中的玉佩，缓缓推开门……",
  "episode_count":1,
  "target_duration_s":50,
  "style_pack":"ancient_chinese"
}'

# 看任务列表
curl "$URL/v1/batch/jobs"
```

✅ 大约 10-20 分钟后（视小云雀 Agent 排队情况），任务变 `completed`，产物在你的 TOS 桶 `manhuaju-prod` 里。

---

## 🔁 后续日常运维

| 操作 | 怎么做 |
|---|---|
| **改代码上线** | 本地改 → `git push` → GHA 自动 build + 自动热更 VeFaaS（5-10min）|
| **查日志** | VeFaaS 控制台 → 函数 → **日志** 标签（直连火山 TLS 日志服务）|
| **调资源** | VeFaaS 控制台 → 函数 → **配置 → 资源** → 直接改 CPU/内存 |
| **看用量/费用** | https://console.volcengine.com/finance/billOverview |
| **紧急止血** | 控制台 → 函数 → **下线** 按钮（API 立即拒绝新请求）|

---

## 💰 成本估算（试点期）

| 资源 | 用量 | 费用/月 |
|---|---|---|
| **VeFaaS API 函数** | 1000 次调用 × 2 vCPU × 5s 平均 | ~¥3 |
| **VeFaaS Worker 函数** | 每分钟 1 次 × 队列空时 0.5s × 30 天 | ~¥15 |
| **VeFaaS Worker 跑任务** | 50 集 × 20min × 2 vCPU | ~¥120 |
| **VCR 镜像存储** | 2GB | ~¥1 |
| **NAS 100GB** | 100GB × ¥0.3 | ~¥30 |
| **TOS 对象存储** | 50 集产物 ~25GB | ~¥3 |
| **公网出流量** | 50 集 × 50MB | ~¥3 |
| **API 调用费**（不在 VeFaaS 内） | 50 集 × 小云雀 + Doubao | ~¥1500 |
| **合计（不算 API）** | | **~¥175/月** |
| **合计（含 API）** | | **~¥1675/月** |

> 对比 ECS：单 ECS（4c8g）固定 ~¥240/月（24×7 占用），无任务时也烧。VeFaaS 试点期省至少 30%，扩张后 API 调用费占大头。

---

## 🆘 常见问题

### Q1：函数冷启动很慢？
- 默认 0 实例时第一次调用要拉镜像 + 启动容器，约 8-15s。
- 解决：函数详情 → 配置 → **预留实例 1**（每天保持 1 个常驻，¥0.2/h ≈ ¥150/月）

### Q2：worker 函数总是失败？
- 大概率是没挂 NAS，`/data/batch.sqlite` 找不到。
- 进 VeFaaS → 函数 → 存储 → 挂载 NAS 到 `/data`，**两个函数要挂同一个 NAS**。

### Q3：HTTP 触发器返回 504？
- 函数超时设的太短。改 `timeout_s` 到 `1800`（30 min）。
- 或者 API 端走"提交即返回 project_id"模式（已实现），客户端轮询 `/v1/projects/{id}` 看状态。

### Q4：私网拉镜像失败？
- VCR 私有仓库需要 VeFaaS 函数有「容器镜像拉取权限」。
- 控制台 → VeFaaS → 函数 → 权限 → 关联角色 → 选 `VCRImagePullRole`（或自建一个带 `cr:GetImage` 权限的角色）。

---

## 🎯 完成标志

- [ ] VCR `manhuaju/manhuaju-autopilot:latest` 镜像存在
- [ ] GHA 最近一次 build 绿色
- [ ] VeFaaS `manhuaju-api` 函数状态绿色就绪
- [ ] VeFaaS `manhuaju-worker` 函数状态绿色就绪
- [ ] `curl <API_URL>/health` 返回 `{"status":"ok"}`
- [ ] 在 Web 控制台投了一个项目，状态 `running` → `completed`
- [ ] TOS 桶里能下载到生成的视频

完成以上，**你的 AI 漫剧 Autopilot 正式以无服务器形态上线了** 🚀
