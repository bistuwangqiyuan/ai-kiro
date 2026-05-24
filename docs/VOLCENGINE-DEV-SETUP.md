# 火山引擎开发环境配置指南

本指南记录 AI 漫剧 Autopilot 项目所需的火山 CLI、TOS 工具与 Cursor MCP 配置。

## 1. 已安装 CLI 工具

| 工具 | 版本 | 路径 | 用途 |
|------|------|------|------|
| `ve` | v1.0.43 | `%USERPROFILE%\.local\bin\ve.exe` | 火山统一 CLI（VCR/VeFaaS/TOS/ECS…） |
| `tosutil` | v4.1.7 | `%USERPROFILE%\.local\bin\tosutil.exe` | TOS 对象存储批量上传/下载 |
| `uvx` | 0.11+ | 系统 PATH | 启动火山官方 MCP Server |

PATH 已写入用户环境变量：`%USERPROFILE%\.local\bin`

## 2. 凭证配置（从 `.env` 自动读取）

项目根目录 `.env` 需包含：

```env
VOLCENGINE_VISUAL_AK=...
VOLCENGINE_VISUAL_SK=...
VOLCENGINE_TOS_AK=...
VOLCENGINE_TOS_SK=...
VOLCENGINE_TOS_REGION=cn-beijing
VOLCENGINE_TOS_ENDPOINT=tos-cn-beijing.volces.com
VOLCENGINE_TOS_BUCKET=manhuaju-assets
```

### 配置 ve CLI

```powershell
ve configure set --profile default --region cn-beijing --access-key $env:VOLCENGINE_VISUAL_AK --secret-key $env:VOLCENGINE_VISUAL_SK
ve sts GetCallerIdentity   # 验证：应返回 AccountId
```

### 配置 tosutil

```powershell
tosutil config -i $env:VOLCENGINE_TOS_AK -k $env:VOLCENGINE_TOS_SK -re cn-beijing -e tos-cn-beijing.volces.com
tosutil ls                 # 验证：应列出 TOS 桶
```

## 3. Cursor MCP（火山官方 10 个 Server）

一键生成 `.cursor/mcp.json`（已在 `.gitignore`，不会提交 Git）：

```powershell
.\deploy\volcengine\setup-mcp.ps1
```

生成的 MCP Server：

| 名称 | 用途 |
|------|------|
| volcengine-tos | TOS 桶/对象检索 |
| volcengine-vefaas | VeFaaS 函数与触发器管理 |
| volcengine-tls | 日志服务 TLS 查询 |
| volcengine-apmplus | APM 链路追踪 |
| volcengine-cdn | CDN 域名与数据分析 |
| volcengine-vke | 容器服务 VKE |
| volcengine-ecs | 云服务器 ECS |
| volcengine-veimagex | 图片服务 veImageX |
| volcengine-iam | 访问控制 IAM |
| volcengine-billing | 费用中心 |

生成后：**重启 Cursor → Settings → MCP** 即可看到并启用。

官方仓库：[volcengine/mcp-server](https://github.com/volcengine/mcp-server)

## 4. VCR 镜像仓库（CI/CD）

GitHub Actions 使用以下 Secrets/Variables（由脚本自动写入）：

| 名称 | 说明 |
|------|------|
| `VCR_USERNAME` | VCR Docker 登录用户名 |
| `VCR_PASSWORD` | VCR Docker 密码 |
| `VCR_REGISTRY_HOST` | 例：`manhuaju-cn-beijing.cr.volces.com` |
| `VCR_NAMESPACE` | 命名空间，例：`manhuaju` |

控制台：[火山 VCR](https://console.volcengine.com/cr)

## 5. 常用命令速查

```powershell
# 列出 VeFaaS 函数
ve vefaas ListFunctions --region cn-beijing

# 列出 VCR 仓库
ve cr ListRepositories --region cn-beijing

# 上传本地目录到 TOS
tosutil cp -r ./api_data/renders tos://manhuaju-assets/renders/ -flat

# 探针测速
tosutil probe
```

## 6. 故障排查

| 现象 | 处理 |
|------|------|
| `ve` 找不到命令 | 新开终端，或 `$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"` |
| tosutil `$tosEndpoint` 解析失败 | 用分离参数：`tosutil config -i ... -k ... -re cn-beijing -e tos-cn-beijing.volces.com` |
| MCP 启动慢 | 首次 `uvx` 会从 GitHub 拉包，需网络；可重试 |
| VCR docker push 401 | 检查 `VCR_USERNAME`/`VCR_PASSWORD` 是否与控制台一致 |
