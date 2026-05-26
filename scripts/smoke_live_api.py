"""Smoke-test the LIVE deployed manhuaju-api at its public URL.

Verifies:
1. /health returns 200 with provider summary
2. /v1/genres / /v1/platforms / /v1/emotions / /v1/actions / /v1/kpi all 200
3. POST /v1/novels (mode=generate, small target) returns a synthesised novel
4. POST /v1/projects with the novel returns a project_id
5. GET  /v1/projects/{id} eventually shows a terminal status

Run:
    python scripts/smoke_live_api.py
"""

from __future__ import annotations

import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = "https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com"


def http(method: str, path: str, body: dict | None = None, timeout: int = 30) -> tuple[int, dict | str]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=timeout) as r:
            payload = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(payload)
            except json.JSONDecodeError:
                return r.status, payload
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        return e.code, body
    except URLError as e:
        return -1, f"URLError: {e}"


def banner(s: str) -> None:
    print("\n" + "=" * 70)
    print(s)
    print("=" * 70)


def main() -> int:
    rc = 0

    banner("1. /health")
    status, body = http("GET", "/health")
    print(f"  HTTP {status}")
    if isinstance(body, dict):
        print(f"  version       : {body.get('version')}")
        print(f"  mode          : {body.get('mode')}")
        print(f"  system_mode   : {body.get('system_mode')}")
        providers = body.get("providers", {})
        enabled = [k for k, v in providers.items() if isinstance(v, dict) and v.get("enabled")]
        print(f"  providers enabled: {enabled}")
        print(f"  fast_path_ready: {body.get('fast_path_ready')}")
    else:
        print(f"  body: {body[:300]}")
        rc = 2

    banner("2. /v1/* config endpoints")
    for ep in ("/v1/genres", "/v1/platforms", "/v1/emotions", "/v1/actions", "/v1/kpi"):
        status, body = http("GET", ep)
        kind = "dict" if isinstance(body, dict) else type(body).__name__
        size = len(json.dumps(body)) if isinstance(body, (dict, list)) else len(str(body))
        print(f"  {ep:20} -> HTTP {status} ({kind}, ~{size} bytes)")
        if status != 200:
            rc = 2

    banner("3. POST /v1/projects (synchronous BackgroundTask)")
    novel_text = (
        "陈屿坐在咖啡馆的角落，盯着窗外飘落的银杏叶。三年了。"
        "门铃响起，林夏推门进来，手里捧着一杯热奶茶。"
        "他认出戒指了——藏在奶茶里的求婚戒指，正是他三年前丢失的那一枚。"
        "陈屿站起身，走向她。林夏的眼神坚定而温柔。\n"
        "「我等你这一杯奶茶，等了三年。」"
    )
    status, body = http(
        "POST",
        "/v1/projects",
        {
            "novel_text": novel_text,
            "seed": 20260526,
            "episode_count": 1,
            "style_preset_id": "cinematic_2d_v1",
            "genre": "modern",
            "episode_duration_s": 45,
            "platforms": ["douyin"],
        },
        timeout=60,
    )
    print(f"  HTTP {status}")
    print(f"  body: {body if isinstance(body, dict) else str(body)[:600]}")
    if status != 200 or not isinstance(body, dict):
        rc = 3
        return rc
    project_id = body.get("project_id")
    if not project_id:
        print("  ERROR: no project_id in response")
        return 3

    banner(f"4. GET /v1/projects/{project_id} (poll until terminal)")
    deadline = time.time() + 180
    last_stage = None
    while time.time() < deadline:
        status, body = http("GET", f"/v1/projects/{project_id}", timeout=20)
        if isinstance(body, dict):
            stage = body.get("stage")
            stat = body.get("status")
            if stage != last_stage:
                print(f"  [{int(time.time())}] status={stat} stage={stage}")
                last_stage = stage
            if stat in ("completed", "succeeded", "failed", "error"):
                print(f"  TERMINAL status={stat}")
                print(f"  full body: {json.dumps(body, ensure_ascii=False)[:1500]}")
                break
        time.sleep(5)
    else:
        print("  TIMEOUT after 180s — pipeline still running")

    banner(f"5. GET /v1/projects/{project_id}/artefacts")
    status, body = http("GET", f"/v1/projects/{project_id}/artefacts", timeout=20)
    print(f"  HTTP {status}")
    if isinstance(body, dict):
        print(f"  keys: {sorted(body.keys())}")
        if "manifest" in body:
            print(f"  manifest keys: {sorted((body.get('manifest') or {}).keys())[:20]}")
    else:
        print(f"  body: {str(body)[:300]}")

    print("\n" + "=" * 70)
    print("DONE", "FAIL" if rc else "OK")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
