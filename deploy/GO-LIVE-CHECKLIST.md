# 上线 Checklist — 火山引擎 VKE（无域名快速试点版）

> 本文档假设你**没有域名**（先用 LoadBalancer 公网 IP 直连），上线后再绑定。
> 总耗时：火山实名+充值 ~15min，VKE 创建 ~10min，部署 ~10min ≈ **35-45 分钟**。

---

## 0️⃣ 前置：注册 + 实名 + 充值

| 步骤 | 链接 | 备注 |
|---|---|---|
| 注册火山引擎 | <https://www.volcengine.com/> | 手机号注册 |
| 实名认证 | <https://console.volcengine.com/iam/realname/personal> | 需要身份证正反面 + 手机号验证（5 min）|
| 充值 | <https://console.volcengine.com/finance/recharge> | **建议先充 ¥500** 可覆盖 50-80 集试点 |

充值后**开通这 4 个服务**（每个点开通即可，不收开通费，按用量计费）：

1. **视觉智能 (CV)**：<https://console.volcengine.com/cv> → "立即开通"
2. **方舟 Ark (大模型)**：<https://console.volcengine.com/ark> → 选 "cn-beijing"
3. **对象存储 TOS**：<https://console.volcengine.com/tos> → "立即开通"
4. **容器服务 (VKE + VCR)**：<https://console.volcengine.com/vke> 和 <https://console.volcengine.com/cr> → 各点开通

---

## 1️⃣ 创建 TOS 桶（5 min，**必须**——小云雀 API 要求图片可公网拉取）

1. <https://console.volcengine.com/tos> → "创建桶"
2. 填表：
   - 桶名：`manhuaju-assets`（必须和 `.env` 里的 `VOLCENGINE_TOS_BUCKET` 一致）
   - 地域：`华北2(北京)` ⚠️ **必须**（小云雀 API 在北京）
   - 访问权限：**公共读** ⚠️ **必须**
   - 存储类型：标准（默认）
3. 创建后进入桶 → 顶部"权限管理" → 跨域规则 → 新建：
   - 来源：`*`
   - 方法：`GET` 勾选
   - 头部：`*`
   - 保存
4. **拿凭证**：<https://console.volcengine.com/iam/keymanage> → "新建密钥" → 把 AccessKey/SecretKey 抄到 `.env` 的 `VOLCENGINE_TOS_AK` / `VOLCENGINE_TOS_SK`（这俩**可以**和下一步视觉的 AK/SK 共用同一对）

---

## 2️⃣ 拿 5 个核心 Key（一一对应 `.env`）

| .env 字段 | 在哪一页拿 | 是否必须 |
|---|---|---|
| `VOLCENGINE_VISUAL_AK/SK` | <https://console.volcengine.com/iam/keymanage> "新建密钥" | ★必须 |
| `VOLCENGINE_ARK_API_KEY` | <https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey> "创建 API Key" | ★必须（VLM 质检+兜底）|
| `ANTHROPIC_API_KEY` | <https://console.anthropic.com/settings/keys> "Create Key" | ★必须（编剧大脑）|
| `ELEVENLABS_API_KEY` | <https://elevenlabs.io/app/settings/api-keys> | ★必须（BGM+SFX）|
| `FAL_KEY` | <https://fal.ai/dashboard/keys> | ★必须（脸锁修复）|
| `DASHSCOPE_API_KEY` | <https://dashscope.console.aliyun.com/apiKey> | 可选（兜底）|

把它们填到 `D:\project\cursor\dev\ai-kiro\.env` 对应行，**保持原本的 UTF-8 编码**。

> 💡 编辑 `.env` 时记得用 VSCode/记事本另存为 UTF-8（不加 BOM）。Cursor IDE 默认就是 UTF-8。

---

## 3️⃣ 创建 VKE 集群（10 min，**点 5 次按钮就行**）

1. <https://console.volcengine.com/vke> → "创建集群"
2. 填表（**复制粘贴下面这些值就行**）：
   | 字段 | 值 |
   |---|---|
   | 集群名称 | `manhuaju-prod` |
   | K8s 版本 | 最新稳定版（默认即可，通常 1.30+）|
   | 网络模式 | VPC-CNI（默认） |
   | VPC | 选默认（或新建） |
   | 节点池配置 | **General — ecs.g3i.xlarge (4c16g)** ★ 试点用 1 个节点就够 |
   | 节点数 | **1** ★ 试点期 |
   | 系统盘 | ESSD-PL0 / 50GB |
3. **付费方式**：**按量付费** ★ 试点期能随时停（包月会被锁 1 月）
4. 创建后等 8-10 分钟（集群拉起）

完成后下载 kubeconfig：

5. 进入集群 → 左侧"集群信息" → 找"kubeconfig" → "下载 kubeconfig" 或"复制"
6. 把内容贴到 `C:\Users\HUAWEI\.kube\config`（没这个目录就新建）

> 也可以在控制台直接点"复制 kubeconfig"，回到 PowerShell 执行：
> ```
> mkdir $env:USERPROFILE\.kube -Force
> notepad $env:USERPROFILE\.kube\config   # 粘贴 → 保存
> ```

---

## 4️⃣ 创建 VCR 镜像仓库 + 凭证（5 min）

1. <https://console.volcengine.com/cr> → "创建仓库"
2. 填表：
   - 命名空间：`manhuaju`（如果已被占用就换 `manhuaju-prod`、`你的名字-manhuaju` 等）
   - 仓库名：`manhuaju-autopilot`
   - 类型：**公开** ★ 试点期，省一个 docker-registry secret
   - 地域：`华北2(北京)`
3. 创建好后**记下完整地址**，应该形如：
   ```
   cr-cn-beijing.volces.com/<你选的命名空间>/manhuaju-autopilot
   ```
4. **创建访问凭证**（给 GitHub Actions 用）：
   - <https://console.volcengine.com/cr> → 右上"用户凭证" → "生成密码"
   - 把 **用户名 + 密码** 抄下来

---

## 5️⃣ 在 GitHub 配 Secrets（让 CI 自动构建+推镜像，2 min）

1. 打开 <https://github.com/bistuwangqiyuan/ai-kiro/settings/secrets/actions>
2. 点 "New repository secret"，添加 2 个：

   | Name | Value |
   |---|---|
   | `VCR_USERNAME` | 上一步抄的 VCR 用户名 |
   | `VCR_PASSWORD` | 上一步抄的 VCR 密码 |

3. 同时编辑 `.github/workflows/build-and-deploy.yml` 顶部的 `IMAGE` 改为你的命名空间，或直接 push 后我帮你改。

---

## 6️⃣ 触发首次构建（你只要 push 代码，剩下 GHA 自动跑）

```powershell
git push origin main
```

然后到 <https://github.com/bistuwangqiyuan/ai-kiro/actions> 看进度，大约 8-12 分钟构建完成（multi-arch 慢一些）。

完成后会自动推到 `cr-cn-beijing.volces.com/<命名空间>/manhuaju-autopilot:latest` 和 `:<git-short-sha>`。

---

## 7️⃣ 部署到 VKE（命令我都给你了，复制粘贴即可）

```powershell
# 0) 检查所有前置条件
.\deploy\scripts\01-check-prereqs.ps1

# 1) 把 .env 转成 K8s Secret（部署后注入到 Pod 环境变量）
.\deploy\scripts\02-create-secret.ps1

# 2) Helm 部署（Tag 用 GHA 跑出来的 short SHA 或 latest）
.\deploy\scripts\03-helm-install.ps1 `
    -Registry cr-cn-beijing.volces.com `
    -Repository <你的命名空间>/manhuaju-autopilot `
    -Tag latest

# 3) 等 1-3 min 后做验收（脚本会自动从 Service 读 EIP）
.\deploy\scripts\04-release-gate.ps1
```

完成后浏览器打开 `http://<EXTERNAL-IP>/`，就是你的线上控制台。

---

## 后续（可选）

- **绑定域名 + HTTPS**：备案后用 `helm upgrade -f values.yaml ...` 走默认 Ingress 配置即可
- **接 RDS PostgreSQL**：开 RDS 拿到 DSN，更新 Secret 加 `POSTGRES_DSN`
- **接监控 VMP**：见 `deploy/README.md` 可观测章节
- **接 CDN 加速**：TOS 桶绑加速域名后填 `VOLCENGINE_TOS_CDN_DOMAIN`

---

## 出问题怎么办

| 症状 | 排查命令 |
|---|---|
| Pod 一直 `ImagePullBackOff` | `kubectl -n manhuaju describe pod <pod-name>` 看具体错误。多半是 `vcr-pull` 凭证错或 VCR 仓库是私有。|
| Pod `CrashLoopBackOff` | `kubectl -n manhuaju logs <pod-name>` 看 Python 报错。常见：`.env` 里 Key 漏填。|
| EXTERNAL-IP 一直 `<pending>` | 火山 CLB 配额满了或子网无 EIP。<https://console.volcengine.com/clb> 看看 |
| `/health` 返回 503 | Pod 没起来，重跑 `04-release-gate.ps1` 前先 `kubectl -n manhuaju get pods` 确认 `Running 1/1`。|
| 跑项目慢 / 卡 | live 模式各家 API 都有延迟（小云雀 5-10min 出 75s 视频），先测 mock。|
