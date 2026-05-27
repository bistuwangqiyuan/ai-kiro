"""User portal acceptance — end-user URL + Simple/Pro console flows."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_BASE = "https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com"


@dataclass
class GateResult:
    name: str
    ok: bool
    note: str = ""
    detail: Any = field(default=None)


def _get(client: httpx.Client, path: str) -> tuple[int, Any]:
    r = client.get(path)
    try:
        return r.status_code, r.json()
    except json.JSONDecodeError:
        return r.status_code, r.text


def _post(client: httpx.Client, path: str, body: dict) -> tuple[int, Any]:
    r = client.post(path, json=body)
    try:
        return r.status_code, r.json()
    except json.JSONDecodeError:
        return r.status_code, r.text


def gate_portal_pages(client: httpx.Client) -> GateResult:
    pages = [
        "/",
        "/console/simple.html",
        "/console/pro.html",
        "/console/guide.html",
        "/guide",
        "/gallery",
        "/console/gallery.html",
        "/docs",
    ]
    fails = []
    for p in pages:
        r = client.get(p)
        if r.status_code != 200:
            fails.append(f"{p}→{r.status_code}")
        elif p.endswith(".html") and "<html" not in r.text.lower():
            fails.append(f"{p}→not html")
    if fails:
        return GateResult("portal_pages", False, "; ".join(fails))
    return GateResult("portal_pages", True, f"{len(pages)} pages OK")


def gate_whitepaper_anchors(client: httpx.Client) -> GateResult:
    code, body = _get(client, "/v1/whitepaper/anchors")
    if code != 200 or not isinstance(body, dict):
        return GateResult("whitepaper_anchors", False, f"HTTP {code}")
    for key in ("cost_p95", "episode_p95_s", "arcface_lead"):
        if key not in body:
            return GateResult("whitepaper_anchors", False, f"missing {key}")
    return GateResult("whitepaper_anchors", True, "anchors OK")


def gate_simple_submit(client: httpx.Client, *, wait_s: int = 180) -> GateResult:
    payload = {
        "mode": "simple",
        "title": "门户验收",
        "novel_text": "她重生回到那年春天，竹林深处，剑光寒凛，照见旧人未死。",
        "language": "zh",
    }
    code, resp = _post(client, "/v1/projects", payload)
    if code != 200 or not isinstance(resp, dict):
        return GateResult("simple_submit", False, f"HTTP {code}", resp)
    pid = resp.get("project_id")
    if not pid:
        return GateResult("simple_submit", False, "no project_id", resp)

    deadline = time.time() + wait_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        c2, state = _get(client, f"/v1/projects/{pid}")
        if c2 == 200 and isinstance(state, dict):
            last = state
            if state.get("status") in ("released", "succeeded", "completed", "failed", "error"):
                break
        time.sleep(3)
    ok = last.get("status") in ("released", "succeeded", "completed")
    return GateResult("simple_submit", ok, f"project_id={pid} status={last.get('status')}", last)


def gate_gallery(client: httpx.Client) -> GateResult:
    code, body = _get(client, "/v1/gallery")
    if code != 200 or not isinstance(body, dict):
        return GateResult("gallery_api", False, f"HTTP {code}")
    videos = body.get("videos") or []
    if len(videos) < 6:
        return GateResult("gallery_api", False, f"expected 6+ videos, got {len(videos)}")
    sample = next((v for v in videos if v.get("is_sample")), videos[0])
    vid = sample.get("video_id")
    if not vid:
        return GateResult("gallery_api", False, "missing video_id")
    r2 = client.head(f"/media/videos/{vid}")
    if r2.status_code not in (200, 307, 308):
        r2 = client.get(f"/media/videos/{vid}")
    if r2.status_code not in (200, 307, 308):
        return GateResult("gallery_api", False, f"stream HTTP {r2.status_code}")
    size = int(r2.headers.get("content-length", 0) or 0)
    if r2.status_code == 200 and size > 0 and size < 1_000_000:
        return GateResult("gallery_api", False, f"video too small ({size} bytes)")
    ct = r2.headers.get("content-type", "")
    if r2.status_code == 200 and "video" not in ct and "octet" not in ct:
        return GateResult("gallery_api", False, f"bad content-type {ct}")
    return GateResult(
        "gallery_api",
        True,
        f"{len(videos)} videos, sample stream OK",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="User portal E2E gate")
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--skip-project", action="store_true")
    args = p.parse_args(argv)

    results: list[GateResult] = []
    with httpx.Client(base_url=args.base.rstrip("/"), timeout=60, verify=False) as client:
        h_code, h_body = _get(client, "/health")
        fast = isinstance(h_body, dict) and h_body.get("fast_path_ready")
        results.append(
            GateResult("health", h_code == 200 and fast, f"fast_path_ready={fast}")
        )
        results.append(gate_portal_pages(client))
        results.append(gate_whitepaper_anchors(client))
        results.append(gate_gallery(client))
        if not args.skip_project:
            results.append(gate_simple_submit(client))

    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"[{mark}] {r.name:<22} — {r.note}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
