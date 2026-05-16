"""Probe DashScope WanX video gen — print full submit + poll responses."""

from __future__ import annotations

import json
import time

import httpx

from manhuaju.core.provider_settings import get_provider_settings


def main() -> None:
    s = get_provider_settings()
    if not s.dashscope_key:
        print("no DASHSCOPE_API_KEY")
        return

    headers_submit = {
        "Authorization": f"Bearer {s.dashscope_key}",
        "X-DashScope-Async": "enable",
        "Content-Type": "application/json",
    }
    body = {
        "model": "wanx2.1-t2v-turbo",
        "input": {
            "prompt": "A young Chinese woman in a futuristic city walks forward, cinematic 2D manga drama"
        },
        "parameters": {"size": "1280*720", "duration": 5, "prompt_extend": True},
    }
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
    print("[submit]", url)
    with httpx.Client(timeout=30) as c:
        r = c.post(url, headers=headers_submit, json=body)
    print(f"  status={r.status_code}")
    print("  body=", r.text[:1000])
    if r.status_code != 200:
        return
    data = r.json()
    task_id = (data.get("output") or {}).get("task_id")
    print(f"  task_id={task_id}")

    if not task_id:
        return

    # Poll a few times, ~30s
    headers_poll = {"Authorization": f"Bearer {s.dashscope_key}"}
    poll_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    for i in range(20):
        time.sleep(3)
        with httpx.Client(timeout=15) as c:
            pr = c.get(poll_url, headers=headers_poll)
        try:
            pd = pr.json()
        except Exception:
            pd = {}
        status = (pd.get("output") or {}).get("task_status")
        print(f"[poll {i:02d}] status={status}")
        if status in ("SUCCEEDED", "FAILED"):
            print(json.dumps(pd, ensure_ascii=False, indent=2)[:2000])
            return


if __name__ == "__main__":
    main()
