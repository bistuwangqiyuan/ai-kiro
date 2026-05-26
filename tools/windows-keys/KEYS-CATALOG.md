# Windows 全局 API Key 库 — 跨项目复用清单

把已验证通过的 API key 一次性写入 Windows **用户级环境变量**（无需管理员、永久生效、跨进程可见），并通过 DPAPI 加密备份到 `%LOCALAPPDATA%\Manhuaju\keys.vault`。后续任何新项目通过 `tools\windows-keys\sync-keys-from-env.ps1` 一键回填 `.env`，省去重复申请。

## 工作流

```mermaid
flowchart LR
  envFile[.env (当前项目)] -->|smoke 通过| install[install-keys-to-user-env.ps1]
  install --> userEnv[Windows User Env Vars]
  install --> vault[DPAPI Vault]
  userEnv --> sync[sync-keys-from-env.ps1<br/>(新项目)]
  sync --> newEnv[新项目 .env]
  userEnv --> list[list-keys.ps1]
```

## 13 个 Key 申请入口 + 限额

| 序号 | Key | 用途 | 申请入口 | 限额 / 备注 |
|:---:|:---|:---|:---|:---|
| 1 | `VOLCENGINE_VISUAL_AK` | 小云雀 Agent 2.0 + 漫剧 Agent + Seedream + Jimeng | <https://console.volcengine.com/iam/keymanage> | 永久；需开通「视觉智能」 3 个应用 |
| 2 | `VOLCENGINE_VISUAL_SK` | 同上 | 同上 | 与 AK 配对，**只在创建时显示一次** |
| 3 | `VOLCENGINE_ARK_API_KEY` | Doubao Seed 1.6 LLM + VLM（编剧 + 多模态质检） | <https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey> | 5000 RPM；¥0.0008 / 1k in tok |
| 4 | `VOLCENGINE_TOS_AK` | 对象存储（参考图、成片归档） | <https://console.volcengine.com/iam/keymanage> | 与 Visual 同一对 AK/SK 即可 |
| 5 | `VOLCENGINE_TOS_SK` | 同上 | 同上 | — |
| 6 | `VOLCENGINE_TOS_BUCKET` | TOS 桶名 | <https://console.volcengine.com/tos> | 自创桶，建议 `manhuaju-assets` |
| 7 | `VOLCENGINE_TOS_ENDPOINT` | TOS Endpoint | 同上 | 默认 `tos-cn-beijing.volces.com` |
| 8 | `DASHSCOPE_API_KEY` | 阿里通义 LLM/TTS/Embedding | <https://dashscope.console.aliyun.com/apiKey> | 60 RPM；首月免费额度 |
| 9 | `DEEPSEEK_API_KEY` | DeepSeek V3.2 备选 LLM | <https://platform.deepseek.com/api_keys> | 60 RPM；¥0.0014 / 1k in tok |
| 10 | `GLM_API_KEY` | 智谱 GLM-4.5 备选 LLM | <https://open.bigmodel.cn/usercenter/apikeys> | 100 RPM；¥0.001 / 1k in tok |
| 11 | `MOONSHOT_API_KEY` | 月之暗面 Kimi 128k | <https://platform.moonshot.cn/console/api-keys> | 200 RPM；¥0.012 / 1k tok |
| 12 | `MISTRAL_API_KEY` | Mistral Large 备选 LLM | <https://console.mistral.ai/api-keys/> | 国际可选；信用卡 |
| 13 | `GROQ_API_KEY` | Groq 高速 LLaMA 70B | <https://console.groq.com/keys> | 国际可选；免费额度 |

### 可选（云上 docker push 需要，不在 13 个核心 key 里）

| Key | 用途 | 申请入口 |
|:---|:---|:---|
| `ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET` | 阿里 FC 备份方案 | <https://ram.console.aliyun.com/manage/ak> |
| `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` | 腾讯云 CAM（CloudBase / CLS / EdgeOne 等） | <https://console.cloud.tencent.com/cam/capi> |
| `VCR_USERNAME` / `VCR_PASSWORD` | 火山 VCR Docker 永久密码 | 控制台 → CR 实例 → 用户管理（Micro tier 不可设；用 GHA 自动 token） |

## 安全模型

1. **存储**：值写入 `HKCU\Environment`（用户范围注册表），重启常驻；非系统范围，**不需要管理员**。
2. **回填**：`sync-keys-from-env.ps1` 仅从环境变量读，**不写回**任何文件；新项目 `.env` 由你审查后保存。
3. **备份**：DPAPI 加密到 `%LOCALAPPDATA%\Manhuaju\keys.vault`，仅当前 Windows 账号可解密；如果误删了用户级 env，可用 `Restore-Keys` 从 vault 还原。
4. **轮换**：`list-keys.ps1` 的 `last_verified` 列提醒你最近一次 smoke 时间；建议每 90 天跑一次 `install`（重新 smoke + 刷新 vault）。
5. **隐藏**：`list-keys.ps1` 永远 mask 中间字符，仅显示首尾 4 位。

## 在新项目里复用（一行命令）

```powershell
# 在新项目根目录执行
.\tools\windows-keys\sync-keys-from-env.ps1 -OutFile .env
```
这会从你的 Windows 用户级 env 把所有 manhuaju 相关 key 写入新项目 `.env`，附带注释；已有同名 key 不会被覆盖（除非加 `-Force`）。
