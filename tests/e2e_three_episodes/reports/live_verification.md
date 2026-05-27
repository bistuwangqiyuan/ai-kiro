# Live deployment verification — 2026-05-27 (portal + backend)

**Base URL:** `https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com`

**用户入口（无需登录）：**

| 页面 | URL |
|------|-----|
| 控制台首页 | `/` |
| Simple 模式 | `/console/simple.html` |
| Pro 模式 | `/console/pro.html` |
| API 文档 | `/docs` |

## Fixes applied this cycle

1. **`deploy/vefaas/provision.py`** — GHA 部署时 LLM/API 密钥只读 `.env` 未回退 `os.environ` → `fast_path_ready=false`。
2. **`scripts/release_gate.py`** — 流水线成功终态为 `released`（非 `succeeded`）。
3. **用户门户** — `project_payload.py` 对接 Simple/Pro 浏览器 payload；`GET /v1/whitepaper/anchors`、`GET /v1/modes`；`config/whitepaper-anchors.json` 打入 Docker 镜像。
4. **VeFaaS 镜像发布** — GHA 构建 tag `160d39f4`；本地 `provision.py --step functions --image-tag 160d39f4` 确保 revision 生效。

## User portal gate (end-user URLs)

```
[PASS] health                 — fast_path_ready=True
[PASS] portal_pages           — 4 pages OK (/, simple, pro, docs)
[PASS] whitepaper_anchors     — anchors OK (Pro 侧栏 KPI)
[PASS] simple_submit          — status=released (~39s)
```

## Release gate (backend)

```
[PASS] health          — mode=hybrid fast_path_ready=true
[PASS] kpi             — thresholds v4-compliant
[PASS] console         — / reachable
[PASS] smoke_endpoints — 4 endpoints OK
[PASS] project_create  — status=released
```

## Reproduce

```powershell
python scripts/user_portal_gate.py --base https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com
python -m scripts.release_gate --base https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com
python scripts/smoke_live_api.py
```

**Note:** `system_mode=hybrid` — LLM 走 live 密钥链，渲染在 Visual 配额不足时 mock-fallback；全 live 视频需 `MANHUAJU_LIVE_MODE=live` + Visual 配额。
