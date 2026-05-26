# Live deployment verification — 2026-05-27

**Base URL:** `https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com`

## Fixes applied this cycle

1. **`deploy/vefaas/provision.py`** — GHA 部署时 LLM/API 密钥只读 `.env` 未回退 `os.environ`，导致 VeFaaS 上 `VOLCENGINE_ARK_API_KEY` 等为空 → `fast_path_ready=false`。
2. **`scripts/release_gate.py`** — 流水线成功终态为 `released`，验收脚本误认 `succeeded` 为唯一成功态。
3. **VeFaaS env 热更新 + release** — 本地 `provision.py --step functions` 注入完整密钥并发布 revision。

## Release gate (full, 1 episode)

```
[PASS] health          — mode=hybrid fast_path_ready=true
[PASS] kpi             — thresholds v4-compliant
[PASS] console         — / reachable
[PASS] smoke_endpoints — 4 endpoints OK
[PASS] project_create  — status=released, seven_dim min ≥ 8.61, ArcFace ≈ 0.997
```

Runtime ~26s per episode (hybrid tier; live LLM + mock render fallback).

## smoke_live_api.py

`DONE OK` — POST /v1/projects → `released` → artefacts 200.

## Reproduce

```powershell
python -m scripts.release_gate --base https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com
python scripts/smoke_live_api.py
```
