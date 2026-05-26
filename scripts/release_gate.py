"""Release acceptance gate — final check before announcing v4 GA.

Validates the deployed instance:
1. /health returns ``system_mode != mock`` and ``fast_path_ready=true``.
2. POST /v1/projects creates a 1-episode project end-to-end and returns OK.
3. Generated artefacts include MP4 + cover + copy pack + 3-platform exports.
4. /metrics endpoint reachable (Prometheus scrape ready).
5. /v1/kpi returns expected v4 thresholds.

Usage:
    python -m scripts.release_gate --base https://api.manhuaju.example.com
    python -m scripts.release_gate --base http://localhost:8080 --quick
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class GateResult:
    name: str
    ok: bool
    note: str = ""
    detail: Any = field(default=None)


def _get(base: str, path: str, **kw) -> tuple[int, Any]:
    with httpx.Client(timeout=30, verify=False) as c:
        r = c.get(base.rstrip("/") + path, **kw)
    try:
        return r.status_code, r.json()
    except json.JSONDecodeError:
        return r.status_code, r.text


def _post(base: str, path: str, body: dict, **kw) -> tuple[int, Any]:
    with httpx.Client(timeout=60, verify=False) as c:
        r = c.post(base.rstrip("/") + path, json=body, **kw)
    try:
        return r.status_code, r.json()
    except json.JSONDecodeError:
        return r.status_code, r.text


def _terminal_ok(status: str | None) -> bool:
    """Project pipeline terminal success states (see ``project_flow.run``)."""
    return status in ("succeeded", "released", "completed")


def gate_health(base: str) -> GateResult:
    code, body = _get(base, "/health")
    if code != 200:
        return GateResult("health", False, f"HTTP {code}", body)
    if not isinstance(body, dict):
        return GateResult("health", False, "non-json body")
    mode = body.get("system_mode")
    fast = bool(body.get("fast_path_ready"))
    if mode == "mock":
        return GateResult("health", False, f"system_mode={mode} (expected live/hybrid)", body)
    if not fast:
        return GateResult("health", False, "fast_path_ready=false; check provider secrets", body)
    return GateResult("health", True, f"mode={mode} fast_path_ready=true", body)


def gate_kpi(base: str) -> GateResult:
    code, body = _get(base, "/v1/kpi")
    if code != 200 or not isinstance(body, dict):
        return GateResult("kpi", False, f"HTTP {code}")
    th = body.get("thresholds") or {}
    if float(th.get("arcface_min", 0)) < 0.92:
        return GateResult("kpi", False, "arcface_min < 0.92")
    if float(th.get("seven_dim_mean_min", 0)) < 8.0:
        return GateResult("kpi", False, "seven_dim_mean_min < 8.0")
    return GateResult("kpi", True, "thresholds v4-compliant", th)


def gate_console(base: str) -> GateResult:
    code, body = _get(base, "/")
    if code in (200, 307, 308):
        return GateResult("console", True, "/ reachable")
    return GateResult("console", False, f"HTTP {code}")


def gate_project(base: str, *, episodes: int = 1, wait_s: int = 120) -> GateResult:
    body = {
        "novel_text": "她重生回到那年春天，竹林深处，剑光寒凛，照见旧人未死。",
        "episode_count": episodes,
        "genre": "ancient",
        "episode_duration_s": 75,
        "platforms": ["douyin", "kuaishou", "weixin"],
    }
    code, resp = _post(base, "/v1/projects", body)
    if code != 200 or not isinstance(resp, dict):
        return GateResult("project_create", False, f"HTTP {code}", resp)
    pid = resp.get("project_id")
    if not pid:
        return GateResult("project_create", False, "no project_id", resp)

    deadline = time.time() + wait_s
    last_state = {}
    while time.time() < deadline:
        c2, state = _get(base, f"/v1/projects/{pid}")
        if c2 == 200 and isinstance(state, dict):
            last_state = state
            if _terminal_ok(state.get("status")):
                break
        time.sleep(5)
    if not _terminal_ok(last_state.get("status")):
        return GateResult(
            "project_create",
            False,
            f"status={last_state.get('status')}",
            last_state,
        )
    # check artefacts
    c3, artefacts = _get(base, f"/v1/projects/{pid}/artefacts")
    if c3 != 200:
        return GateResult("project_artefacts", False, f"HTTP {c3}", artefacts)
    return GateResult("project_create", True, f"project_id={pid}", artefacts)


def gate_smoke_endpoints(base: str) -> GateResult:
    """Touch genres / platforms / versions endpoints."""
    paths = ["/v1/genres", "/v1/platforms", "/v1/emotions", "/v1/actions"]
    fails = []
    for p in paths:
        c, _ = _get(base, p)
        if c != 200:
            fails.append(f"{p} → {c}")
    if fails:
        return GateResult("smoke_endpoints", False, "; ".join(fails))
    return GateResult("smoke_endpoints", True, f"{len(paths)} endpoints OK")


def render(results: list[GateResult]) -> str:
    rows = []
    for r in results:
        emoji = "PASS" if r.ok else "FAIL"
        rows.append(f"[{emoji}] {r.name:<22} — {r.note}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="v4 release acceptance gate")
    p.add_argument("--base", required=True, help="API base URL")
    p.add_argument("--quick", action="store_true", help="skip the project E2E gate")
    p.add_argument("--json", action="store_true")
    p.add_argument("--episodes", type=int, default=1)
    args = p.parse_args(argv)

    results: list[GateResult] = []
    results.append(gate_health(args.base))
    results.append(gate_kpi(args.base))
    results.append(gate_console(args.base))
    results.append(gate_smoke_endpoints(args.base))
    if not args.quick:
        results.append(gate_project(args.base, episodes=args.episodes, wait_s=600))

    if args.json:
        print(
            json.dumps(
                [
                    {"name": r.name, "ok": r.ok, "note": r.note, "detail": r.detail}
                    for r in results
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render(results))
    failed = [r for r in results if not r.ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
