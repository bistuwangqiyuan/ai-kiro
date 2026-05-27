# Live deployment verification — 2026-05-27 (auth + portal + gallery)

**Base URL:** `https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com`

**用户入口（公开页面）：**

| 页面 | URL | 认证 |
|------|-----|------|
| 控制台首页 | `/` | 公共，登录后启用「只看我的」 |
| 简易模式 | `/console/simple.html` | 公共（登录后记录归属） |
| 专业模式 | `/console/pro.html` | 公共（登录后记录归属） |
| 视频广场 | `/gallery` | 公共 |
| 使用说明 | `/guide` 或 `/console/guide.html` | 公共 |
| 登录 / 注册 | `/login` 或 `/console/login.html` | 公共 |
| API 文档 | `/docs` | 公共 |

**预置测试账号（启动时自动入库）：**

| 用户名 | 密码 |
|--------|------|
| `test1@139.com` | `123456` |
| `test2@139.com` | `123456` |

## Latest deploy

- Image: `manhuaju-cn-beijing.cr.volces.com/manhuaju/manhuaju-autopilot:788204ca`
- Function: `manhuaju-api` (id `ex9xkzt4`, revision 14, instance `Ready`)
- Source commit: `788204c` (top), includes auth feature `9a8c50d`.
- Provisioned via:
  ```powershell
  python deploy/vefaas/provision.py --step functions --image-tag 788204ca
  python deploy/vefaas/promote_latest.py --function-id ex9xkzt4
  ```
  (the second step shouldn't be needed after the `_release` polling fix in
  this commit, but it remains as a manual escape hatch.)

## User portal gate (end-user URLs + auth + project lifecycle)

```
[PASS] health                 — fast_path_ready=True
[PASS] portal_pages           — 11 pages OK
[PASS] whitepaper_anchors     — anchors OK
[PASS] gallery_api            — 6 videos, ranged GET OK (3113293 bytes total)
[PASS] auth_login             — token len=43 me=OK
[PASS] auth_seed_t2           — seed t2 OK
[PASS] auth_negative          — wrong-pass + missing/invalid bearer all 401
[PASS] simple_submit          — project_id=proj_c8712bd90c41 status=released
[PASS] auth_my_projects       — submitted+listed proj_7fef7f9b0d4b owner=test1@139.com
```

All 9 gates green. Coverage:

- **Static pages**: `/`, `/console/{simple,pro,guide,login,gallery}.html`, `/console/auth.js`, `/guide`, `/gallery`, `/login`, `/docs`.
- **Auth backend**: `/v1/auth/{login,register,me}` happy + negative paths (wrong password → 401, no/invalid bearer → 401).
- **Anonymous flow**: `simple_submit` posts a project without a token, polls until `released`.
- **Authenticated flow**: `auth_my_projects` logs in as `test1@139.com`, submits, then verifies (a) `owner==test1@139.com`, (b) `mine=1` only returns own projects, (c) `mine=1` without bearer returns 401, (d) public list still surfaces the project.
- **Gallery streaming**: ranged GET (`bytes=0-65535`) confirms a 3.1 MB sample MP4 is reachable through the gateway without truncation.

## Reproduce

```powershell
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"
python scripts/user_portal_gate.py --base https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com
```

For an automated build → deploy → verify loop:

```powershell
python scripts/deploy_loop.py --base https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com
```

## Notes

- `system_mode=hybrid` — LLM live, render may mock-fallback when Visual quota is exhausted.
- Auth uses opt-in opaque bearer tokens (`secrets.token_urlsafe(32)`) backed by SQLite; passwords are stored as `scrypt$<salt>$<hash>` (stdlib only, no extra deps).
- Test accounts are seeded at app construction time, so cold container starts and TestClient invocations both have them available without waiting for the asynchronous startup hook.
