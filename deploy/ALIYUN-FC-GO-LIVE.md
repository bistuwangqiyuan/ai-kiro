# 🚀 AI 漫剧 Autopilot v4 — 阿里云 FC 3.0 一键上线（推荐 / 最简单）

> 国内 serverless 首选方案。完全国内化（ACR + FC），按调用计费，闲时缩到 0。
> 总耗时：**~10 分钟**（含 GHA 多架构 build）。

---

## ✅ 为啥选阿里云 FC 而不是火山 VeFaaS

| | 火山 VeFaaS（试过）| **阿里云 FC（推荐）** |
|---|---|---|
| 镜像仓库 docker 密码 | 小微版要控制台手工设 | API 自动签发临时 token，零手工 |
| OpenAPI SDK 完整度 | 一般 | 极完整（FC 3.0 模型字段全公开）|
| 容器拉镜像鉴权 | 需要 IAM 角色 | 同账号 FC 拉 ACR 镜像免认证 |
| 文档/社区/教程 | 较少 | 海量中文教程 |
| 开通成本 | 免费 | 免费（含每月 100w 次调用免额）|

---

## 📋 上线 3 步

### 步骤 1 — 阿里云控制台开通 2 个服务（一次性，30 秒）

| 服务 | 链接 | 操作 |
|---|---|---|
| **容器镜像 ACR** | https://cr.console.aliyun.com | 点「开通服务」（个人版永久免费）|
| **函数计算 FC** | https://fcnext.console.aliyun.com | 点「立即开通」（免费）|

### 步骤 2 — 拿阿里云 AccessKey + 填进 .env（1 分钟）

打开 **https://ram.console.aliyun.com/manage/ak**

- 选「为RAM用户创建AccessKey」或「为主账号创建AccessKey」
- 拷贝 AccessKey ID 和 Secret
- 编辑 `.env`，加这两行：

```
ALIBABA_CLOUD_ACCESS_KEY_ID=LTAI5tXXXXXXXXXXXX
ALIBABA_CLOUD_ACCESS_KEY_SECRET=YYYYYYYYYYYYYYYYYYY
```

### 步骤 3 — 一键脚本（~10 分钟，全自动）

```powershell
cd D:\project\cursor\dev\ai-kiro
.\deploy\aliyun-fc\aliyun-fc-go-live.ps1
```

脚本会自动：

1. 检查工具（gh / python / 阿里云 SDK）
2. 调 ACR OpenAPI：
   - 找到你的 ACR 实例
   - 建命名空间 `manhuaju`（如不存在）
   - 建仓库 `manhuaju-autopilot`（如不存在）
   - 调 GetAuthorizationToken 拿临时 docker 凭证（1 小时有效）
3. 用 `gh` 把 4 个 Secrets（含 ACR/Aliyun）和 5 个 Variables 自动写入 GitHub
4. push 一个空 commit → 触发 GHA 自动 build + 推 ACR
5. 轮询 GHA 直到 build 完成（~8-12 min）
6. 调 FC OpenAPI：
   - 创建 `manhuaju-api` 函数 + HTTP 触发器
   - 创建 `manhuaju-worker` 函数 + 定时触发器（每分钟）
7. 自动 echo 出公网 URL：`https://manhuaju-api-xxxxx.fcapp.run`

---

## 🔬 验证

完成后：

```powershell
$URL = "https://manhuaju-api-xxxxx.fcapp.run"   # 替换为脚本输出的 URL
curl $URL/health
# 期望: {"status":"ok",...}

curl -X POST $URL/v1/projects -H 'Content-Type: application/json' -d '{
  "title":"上线测试",
  "novel_text":"夜雨连绵，林深听见门外的脚步…",
  "episode_count":1,
  "target_duration_s":50,
  "style_pack":"ancient_chinese"
}'

Start-Process "$URL/console.html"
```

---

## 💰 成本估算（试点期）

| 资源 | 单价 | 月用量假设 | 月费 |
|---|---|---|---|
| **FC vCPU·s** | ¥0.0001327/s | 100 集 × 20min × 2c = 240k s | **¥32** |
| **FC 内存** | ¥0.0000079/GB·s | 100 集 × 20min × 4G = 480k GB·s | **¥4** |
| **FC 调用次数** | ¥0.009/万次 | 1w 次 | **¥0.01** |
| **ACR 个人版存储** | 免费 | 2GB 镜像 | **¥0** |
| **FC 公网出流量** | ¥0.5/GB | 100 集 × 50MB = 5GB | **¥2.5** |
| **API 调用费**（外部）| - | 小云雀 + Doubao | ~¥1500 |
| **小计（FC 内）** | | | **~¥40/月** |
| **总计（含 API）** | | | **~¥1540/月** |

> FC 每月有 **100 万次调用 + 40 万 vCPU·s** 免费额度，试点期可能完全不收 FC 钱。

---

## 🆘 常见问题

### Q1: GHA build 失败 docker login `unauthorized`？
- 因为 ACR 临时 token 1 小时过期。重跑 `.\deploy\aliyun-fc\aliyun-fc-go-live.ps1 -SkipProvision -SkipBuild` 会重新生成 token。
- 或者直接重跑完整脚本：`.\deploy\aliyun-fc\aliyun-fc-go-live.ps1`

### Q2: FC 函数冷启动慢？
- 默认 idle keepalive 1 小时；第一次调用约 8-15 秒。
- 加预留实例：FC 控制台 → 函数 → 配置 → 预留实例数=1（¥0.16/h ≈ ¥115/月，可选）

### Q3: 函数超时？
- 默认 30 min。单集生成 < 25 min 应该够用。
- 如果某些复杂场景超时，FC 控制台 → 配置 → 超时时间改大（最大 24 小时）

### Q4: 用控制台手工建函数行不行？
- 可以。控制台 FC 3.0 → 创建函数 → 容器镜像 → 选你的 ACR 镜像 → 配置 CPU/内存/超时/环境变量 → 创建 HTTP 触发器
- 但是脚本一键 = 不会漏配置

---

## 🎯 完成标志

- [ ] 在 ACR 控制台看到 `manhuaju/manhuaju-autopilot:latest` 镜像
- [ ] GHA `build-aliyun-fc` 最近一次 run 绿色
- [ ] FC 控制台看到 `manhuaju-api` + `manhuaju-worker` 两个函数（绿色就绪）
- [ ] `curl <API_URL>/health` 返回 `{"status":"ok"}`
- [ ] Web 控制台投了一个项目，几分钟后状态变 `running` → `completed`

完成以上，**你的 AI 漫剧 Autopilot 以阿里云 serverless 形态上线了** 🚀
