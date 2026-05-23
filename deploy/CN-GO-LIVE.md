# 🚀 国内极简上线指南 — 1 台火山 ECS 直接出片

> 适用场景：你在国内、没有境外信用卡、不想搞 K8s，只想最快上线让用户能跑起来。
>
> **预计总耗时：45-60 分钟**（火山实名等待 15-30min + ECS 创建 3min + 部署 8min + 试跑 1 集 15min）
>
> 总成本：试点期月 **¥150-300**（1 台 ECS + TOS 存储 + 视频生成按量）

---

## 0️⃣ 概览：你只需要这些东西

| 类目 | 是什么 | 用什么 | 月成本（试点期）|
|---|---|---|---|
| 一台云服务器 | 跑 docker compose | **火山 ECS 4c8g**（ecs.g3i.xlarge）| ¥120 (按量) |
| 对象存储 | 给小云雀拉参考图 | **火山 TOS** | ¥10-30 |
| 视频生成 | 25-75s 漫剧 | **火山小云雀 Agent 2.0** | ¥39/集 |
| 图像 | 角色 + 场景 | **火山 Seedream + 即梦** | ¥0.3-0.5/张 |
| 编剧大脑 | 小说分集脚本 | **火山方舟 Doubao Seed 1.6** | ¥0.005/千 token |
| BGM/SFX | 背景音乐 | **本地预制 CC0 曲库** | ¥0 |
| 反代+TLS | HTTPS | **Caddy 自动 Let's Encrypt** | ¥0 |

**完全国内栈，零境外依赖，无需 VPN，无需信用卡。**

---

## 1️⃣ 火山引擎账号（一次性，15-30 分钟）

1. **注册 + 实名**：
   - 注册：<https://www.volcengine.com/>
   - 个人实名：<https://console.volcengine.com/iam/realname/personal>（5-15 min 审核）

2. **充值 ¥500**（足够 5-10 集试点）：
   - <https://console.volcengine.com/finance/recharge>

3. **开通 3 个服务**（每个点"立即开通"即可，按量计费）：
   - 视觉智能 (CV)：<https://console.volcengine.com/cv>
   - 方舟 (Ark)：<https://console.volcengine.com/ark>
   - 对象存储 (TOS)：<https://console.volcengine.com/tos>

---

## 2️⃣ 创建 TOS 桶（5 min）

⚠️ **必须**：小云雀 API 要求参考图能公网拉取。

1. <https://console.volcengine.com/tos> → "创建桶"
2. 填这几项（**复制粘贴**）：
   | 字段 | 值 |
   |---|---|
   | 桶名 | `manhuaju-assets` |
   | 地域 | **华北2(北京) `cn-beijing`** |
   | 访问权限 | **公共读** ⚠️ 必须 |
3. 创建后进入桶 → 顶部"权限管理" → "跨域规则" → 新建：
   - 来源：`*`
   - 方法：勾选 **GET**
   - 头部：`*`

---

## 3️⃣ 获取 3 把 Key（10 min，跟着图片点）

| 路径 | 拿到什么 → 填到 `.env` 哪一行 |
|---|---|
| <https://console.volcengine.com/iam/keymanage> → "新建密钥" | `AccessKey ID` → `VOLCENGINE_VISUAL_AK` <br> `SecretAccessKey` → `VOLCENGINE_VISUAL_SK` <br>（**TOS 也用同一对**，填到 `VOLCENGINE_TOS_AK/SK`）|
| <https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey> → "创建 API Key" | 直接复制 → `VOLCENGINE_ARK_API_KEY` |

> 💡 这 3 把 Key 是**唯一必填**的！其它（DashScope/DeepSeek/Anthropic 等）全部可选。

---

## 4️⃣ 创建一台 ECS（3 min）

1. <https://console.volcengine.com/ecs/createInstance>
2. 填表：
   | 字段 | 值 |
   |---|---|
   | 地域 | **华北2(北京)** ⚠️ 和 TOS 同区域 |
   | 镜像 | **Ubuntu 22.04 LTS** |
   | 规格 | **通用型 g3i — ecs.g3i.xlarge (4c8g)** |
   | 系统盘 | ESSD-PL0 / 50GB（最小） |
   | 公网 IP | **分配** + 按量计费 5Mbps |
   | 付费方式 | **按量付费**（随时停） |
   | 安全组 | 默认 + 加规则：**开放 80 / 443 / 22 入站** |
   | 登录方式 | **设置 root 密码**（最简单）或 SSH Key |

3. 创建后等 1-2 分钟，**记下公网 IP**。

---

## 5️⃣ 一键部署（在你本地 Windows 跑，约 8-12 分钟）

打开 PowerShell，进入项目目录：

```powershell
cd D:\project\cursor\dev\ai-kiro

# 编辑 .env 填入 3 把 Key（用 notepad 或 cursor）
notepad .env
```

**`.env` 至少要填这 5 行**：

```
VOLCENGINE_VISUAL_AK=<刚拿到的 AK>
VOLCENGINE_VISUAL_SK=<刚拿到的 SK>
VOLCENGINE_ARK_API_KEY=<刚拿到的 ARK Key>
VOLCENGINE_TOS_AK=<同 VISUAL_AK>
VOLCENGINE_TOS_SK=<同 VISUAL_SK>
```

填好后**一行命令上线**：

```powershell
.\deploy\cn-easy\cn-deploy-remote.ps1 -EcsIp <ECS公网IP> -EcsUser root
```

> 首次 SSH 会让你输 root 密码（火山控制台创建 ECS 时设的那个）。
> 也可以用 SSH Key：`-SshKey C:\Users\HUAWEI\.ssh\id_rsa`

这条命令会**自动**做这些事：
- SSH 到 ECS → 装 Docker（用阿里云加速源）→ 配国内镜像源
- git clone 代码到 `/opt/manhuaju`
- 上传你本地的 `.env` 到 ECS
- 构建多架构 Docker 镜像
- 用 docker compose 起 3 个服务：api / worker / caddy
- 等到 `/health` 返回 ok 才算成功
- 输出可访问的 URL

---

## 6️⃣ 立即验收

部署成功后浏览器打开：

- **Web 控制台**：`http://<ECS公网IP>/`
- **Swagger API 文档**：`http://<ECS公网IP>/docs`
- **KPI 看板**：`http://<ECS公网IP>/v1/kpi`

在 Swagger 里 `POST /v1/projects` 提交一段小说，等 15-25 分钟就能拿到第一集成片。

---

## 7️⃣ （可选）绑定 HTTPS 域名

如果有备案域名 + 想要 HTTPS：

1. **DNS 解析到 ECS 公网 IP**：
   - 火山云解析：<https://console.volcengine.com/dns>
   - 或阿里云、腾讯云等 DNS 服务

2. **在 ECS 上的 `.env` 里加一行**：
   ```
   MANHUAJU_DOMAIN=api.yourdomain.com
   ```

3. **重启 Caddy**：
   ```powershell
   .\deploy\cn-easy\cn-deploy-remote.ps1 -EcsIp <IP> -RestartOnly
   ```

Caddy 会**自动**申请 Let's Encrypt 证书（约 30 秒），之后访问 `https://api.yourdomain.com` 直接通。

---

## 8️⃣ 常用运维

```powershell
# 重新部署（拉最新代码 + 重启）
.\deploy\cn-easy\cn-deploy-remote.ps1 -EcsIp <IP>

# 仅重启
.\deploy\cn-easy\cn-deploy-remote.ps1 -EcsIp <IP> -RestartOnly

# 查看实时日志
ssh root@<IP> "cd /opt/manhuaju && docker compose -f deploy/cn-easy/docker-compose.cn.yml logs -f --tail 200"

# 停服
ssh root@<IP> "cd /opt/manhuaju && docker compose -f deploy/cn-easy/docker-compose.cn.yml down"

# 进容器调试
ssh root@<IP> "docker exec -it manhuaju-api /bin/bash"
```

---

## 出问题排查表

| 症状 | 原因 | 修复 |
|---|---|---|
| `cn-deploy.sh` 报缺 `.env` 必填项 | `.env` 里 5 个核心 Key 没填全 | 编辑 `.env` 后重跑 |
| `/health` 返回 503 / 一直不 ok | 容器还没起来 | `ssh root@<IP> "docker compose ... ps"` 看容器状态，看 logs |
| docker pull 慢 | 镜像源被屏蔽 | 脚本已自动配 5 个国内镜像源；若仍慢可换网络 |
| Caddy 申请 SSL 卡住 | 80/443 入站没开 | 火山控制台 → 安全组 → 加规则 |
| 小云雀返回 401 | AK/SK 错或 ReqKey 没开通 | 控制台→视觉智能→应用列表 看是否已开通 `skylark_video_agent_v2_with_ref` |
| TOS 上传失败 | 桶名错 / region 错 / 不是公共读 | 见步骤 2️⃣ |
| 单集生产 > 30min | 小云雀排队 | 控制台开通"小云雀 - 商用并发" |

---

## 进阶：用 Helm + VKE（大规模时升级）

> 试点期不用看本节。当你月产能 > 500 集、需要弹性伸缩时再考虑。

参考 `deploy/GO-LIVE-CHECKLIST.md`（VKE 完整版指南）+ `deploy/helm/manhuaju/values.yaml`。
