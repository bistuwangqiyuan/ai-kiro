"""Probe DashScope WanX with several pipeline-style prompts.

Verifies that the new ``RealWanXAdapter._compose_prompt`` output is
accepted by WanX and reaches ``task_status=SUCCEEDED`` rather than
``FAILED`` like the previous pipe-separated form did.
"""

from __future__ import annotations

import json
import sys
import time

import httpx

from manhuaju.adapters.render.real_wanx_adapter import RealWanXAdapter
from manhuaju.core.provider_settings import get_provider_settings

SAMPLES = [
    {
        "prompt": "establish wide shot, soft morning light, intimate framing",
        "characters": [{"name": "yunque", "archetype": "protagonist"}],
        "location_id": "old_city_alley",
        "mood": "wistful",
        "key_action": "looks up toward the distant skyline",
    },
    {
        "prompt": "medium close-up | tense dialogue | warm rim light",
        "characters": [
            {"name": "yunque", "archetype": "protagonist"},
            {"name": "mentor", "archetype": "guide"},
        ],
        "location_id": "training_yard",
        "mood": "tense",
        "key_action": "exchange a sharp glance before the duel",
    },
]


def submit(key: str, prompt: str) -> str | None:
    headers = {
        "Authorization": f"Bearer {key}",
        "X-DashScope-Async": "enable",
        "Content-Type": "application/json",
    }
    body = {
        "model": "wanx2.1-t2v-turbo",
        "input": {"prompt": prompt},
        "parameters": {"size": "1280*720", "duration": 5, "prompt_extend": True},
    }
    with httpx.Client(timeout=30) as c:
        r = c.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis",
            headers=headers,
            json=body,
        )
    print(f"  submit status={r.status_code}")
    if r.status_code != 200:
        print(f"  body={r.text[:600]}")
        return None
    return (r.json().get("output") or {}).get("task_id")


def poll(key: str, task_id: str, max_iter: int = 30) -> str:
    headers = {"Authorization": f"Bearer {key}"}
    url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    last = "?"
    for i in range(max_iter):
        time.sleep(3)
        with httpx.Client(timeout=15) as c:
            r = c.get(url, headers=headers)
        try:
            data = r.json()
        except Exception:
            data = {}
        status = (data.get("output") or {}).get("task_status", "?")
        print(f"  poll {i:02d} status={status}")
        last = status
        if status in {"SUCCEEDED", "FAILED"}:
            if status == "FAILED":
                print(json.dumps(data, ensure_ascii=False, indent=2)[:1200])
            return status
    return last


def main() -> int:
    s = get_provider_settings()
    if not s.dashscope_key:
        print("no DASHSCOPE_API_KEY")
        return 1
    from manhuaju.core.cost_tracker import CostTracker

    adapter = RealWanXAdapter(settings=s, cost=CostTracker())
    success = 0
    for i, sample in enumerate(SAMPLES, 1):
        prompt = adapter._compose_prompt(**sample)
        print(f"\n=== sample {i}: ===")
        print(f"  composed: {prompt!r}")
        tid = submit(s.dashscope_key, prompt)
        if not tid:
            continue
        print(f"  task_id={tid}")
        status = poll(s.dashscope_key, tid)
        if status == "SUCCEEDED":
            success += 1
    print(f"\n{success}/{len(SAMPLES)} prompts succeeded")
    return 0 if success == len(SAMPLES) else 2


if __name__ == "__main__":
    sys.exit(main())
