"""Verify the live VeFaaS deployment is actually running real video generation.

Submits a 1-episode 30 s project anonymously, polls until done, then checks
the public gallery entry to confirm the published video is the real
``final_mp4`` from the pipeline (``is_sample=False``) rather than a curated
``web/samples`` fallback.

Usage:

    uv run python scripts/verify_real_render.py \\
        --base https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com \\
        --wait-s 1500

The script prints a single PASS / FAIL line per check + a final summary.
Exit code 0 = real render confirmed; non-zero = something fell back to a
sample (the verbose log identifies which check failed).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import httpx

DEFAULT_BASE = "https://sd8ap3btqc6mqij6t2bsg.apigateway-cn-beijing.volceapi.com"


def _get(client: httpx.Client, path: str) -> tuple[int, Any]:
    r = client.get(path)
    try:
        return r.status_code, r.json()
    except json.JSONDecodeError:
        return r.status_code, r.text


def _post(client: httpx.Client, path: str, body: dict[str, Any]) -> tuple[int, Any]:
    r = client.post(path, json=body)
    try:
        return r.status_code, r.json()
    except json.JSONDecodeError:
        return r.status_code, r.text


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument(
        "--wait-s",
        type=int,
        default=1500,
        help="Polling timeout in seconds (default 1500 = 25 min, just under FaaS timeout)",
    )
    p.add_argument(
        "--allow-sample",
        action="store_true",
        help="Treat is_sample=True as a soft warning (default: hard fail)",
    )
    p.add_argument(
        "--novel-text",
        default=(
            "她推开木门，烛火轻摇，照见少年眉眼如旧。"
            "他笑着说：『我等你一千年了。』"
            "她伸出手，触到他指尖，那一刻整座长安都安静了。"
        ),
    )
    p.add_argument("--title", default="真实生成验证")
    args = p.parse_args(argv)

    client = httpx.Client(base_url=args.base.rstrip("/"), timeout=60, verify=False)

    print(f"[1/5] GET /health on {args.base}")
    code, health = _get(client, "/health")
    if code != 200 or not isinstance(health, dict):
        print(f"  FAIL: /health returned HTTP {code}")
        return 2
    fast_ready = bool(health.get("fast_path_ready"))
    sysmode = health.get("system_mode") or ""
    print(
        f"  OK  system_mode={sysmode} fast_path_ready={fast_ready} "
        f"providers={list(health.get('providers') or {})}"
    )
    if not fast_ready:
        print(
            "  WARN: fast_path_ready=false — provider keys are missing on the "
            "function. Real generation cannot run; expect fallback to samples."
        )

    print("[2/5] POST /v1/projects (anonymous, 1 ep × 30 s)")
    payload = {
        "mode": "simple",
        "title": args.title,
        "novel_text": args.novel_text,
        "language": "zh",
    }
    code, resp = _post(client, "/v1/projects", payload)
    if code != 200 or not isinstance(resp, dict):
        print(f"  FAIL: submit HTTP {code} body={resp!r}")
        return 3
    pid = resp.get("project_id")
    if not pid:
        print(f"  FAIL: no project_id in response: {resp!r}")
        return 3
    print(f"  OK  project_id={pid} owner={resp.get('owner') or '<anon>'}")

    print(f"[3/5] Poll /v1/projects/{pid} until terminal (max {args.wait_s} s)")
    deadline = time.time() + args.wait_s
    last: dict[str, Any] = {}
    poll_no = 0
    while time.time() < deadline:
        poll_no += 1
        elapsed = int(time.time() - (deadline - args.wait_s))
        c2, state = _get(client, f"/v1/projects/{pid}")
        if c2 == 200 and isinstance(state, dict):
            last = state
            status = state.get("status") or "?"
            stage = state.get("stage") or "-"
            print(f"  [{elapsed:>4}s #{poll_no}] status={status:<10} stage={stage}")
            if status in ("released", "succeeded", "completed", "failed", "error"):
                break
        else:
            print(f"  [poll {poll_no}] HTTP {c2}")
        time.sleep(10)
    final_status = (last.get("status") or "").lower()
    if final_status not in ("released", "succeeded", "completed"):
        print(f"  FAIL: project did not complete (last status={final_status!r})")
        print(f"  last={json.dumps(last, ensure_ascii=False)[:600]}")
        return 4
    print(f"  OK  final status={final_status}")

    print(f"[4/5] GET /v1/gallery?project_id={pid}")
    code, gal = _get(client, f"/v1/gallery?project_id={pid}")
    if code != 200 or not isinstance(gal, dict):
        print(f"  FAIL: gallery HTTP {code}")
        return 5
    videos = gal.get("videos") or []
    if not videos:
        print("  FAIL: gallery returned 0 videos for this project")
        return 5
    v = videos[0]
    print(
        "  OK  video_id={vid} ep={ep} is_sample={is_sample} "
        "local_video={lv}".format(
            vid=v.get("video_id"),
            ep=v.get("episode_id"),
            is_sample=v.get("is_sample"),
            lv=v.get("local_video"),
        )
    )

    print("[5/5] HEAD /media/videos/{video_id}")
    head = client.head(f"/media/videos/{v.get('video_id')}")
    head_size = int(head.headers.get("content-length", 0) or 0)
    head_ct = head.headers.get("content-type", "")
    print(f"  OK  HTTP {head.status_code} size={head_size} content-type={head_ct}")

    print()
    print("=" * 60)
    if v.get("is_sample"):
        msg = (
            "  RESULT: gallery entry is a CURATED SAMPLE (is_sample=True)\n"
            "  This means the pipeline did not produce a real final_mp4\n"
            "  for this project, so the gallery fell back to web/samples.\n"
            "  Possible causes:\n"
            "    1. Provider keys missing on the function (fast_path_ready=false above)\n"
            "    2. Real adapter raised an error and silently fell back to mock\n"
            "    3. Generated MP4 file was not findable on local disk after rendering\n"
            "  Check /v1/diagnostics or VeFaaS function logs for [run] lines."
        )
        print(msg)
        return 0 if args.allow_sample else 6

    print(
        "  RESULT: gallery entry is a REAL generation (is_sample=False)\n"
        f"  local_video={v.get('local_video')}\n"
        f"  HEAD content-length={head_size} bytes\n"
        "  Real video generation flow is working end-to-end."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
