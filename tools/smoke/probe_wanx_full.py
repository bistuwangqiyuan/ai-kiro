"""Reproduce the EXACT WanX request body the live pipeline sends."""

from __future__ import annotations

import json
import time

import httpx

from manhuaju.core.provider_settings import get_provider_settings

PROMPT = (
    "A young East Asian protagonist named yunque, looks up toward the distant skyline, "
    "in old city alley, a wistful atmosphere, establish wide shot, soft morning light, "
    "intimate framing, cinematic 2D manga drama style, soft lighting, painterly colors, "
    "smooth motion"
)


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
        "input": {"prompt": PROMPT[:1500]},
        "parameters": {
            "size": "1280*720",
            "duration": 5,
            "prompt_extend": True,
            "seed": 1234567 & 0x7FFFFFFF,
        },
    }
    print("[submit] body=", json.dumps(body, ensure_ascii=False))
    with httpx.Client(timeout=30) as c:
        r = c.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis",
            headers=headers_submit,
            json=body,
        )
    print(f"  status={r.status_code} body={r.text[:600]}")
    if r.status_code != 200:
        return
    tid = (r.json().get("output") or {}).get("task_id")
    print(f"  task_id={tid}")
    if not tid:
        return
    headers_poll = {"Authorization": f"Bearer {s.dashscope_key}"}
    for i in range(30):
        time.sleep(3)
        with httpx.Client(timeout=15) as c:
            pr = c.get(
                f"https://dashscope.aliyuncs.com/api/v1/tasks/{tid}", headers=headers_poll
            )
        try:
            pd = pr.json()
        except Exception:
            pd = {}
        st = (pd.get("output") or {}).get("task_status", "?")
        print(f"  poll {i:02d} status={st}")
        if st in {"SUCCEEDED", "FAILED"}:
            print(json.dumps(pd, ensure_ascii=False, indent=2)[:2000])
            return


if __name__ == "__main__":
    main()
