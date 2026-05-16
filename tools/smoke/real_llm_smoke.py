"""Manual smoke test for RealLLMAdapter — invokes real APIs.

Run with: `python tools/smoke/real_llm_smoke.py`
Skipped automatically by pytest because filename does not start with `test_`.
"""

from __future__ import annotations

import sys
import time

from manhuaju.adapters.llm.real_llm_adapter import RealLLMAdapter
from manhuaju.core.cost_tracker import CostTracker
from manhuaju.core.provider_settings import get_provider_settings


def main() -> int:
    settings = get_provider_settings()
    eligible = [e for e in settings.llm_endpoints if e.enabled and e.api_key]
    print(f"[smoke] eligible providers: {[e.name for e in eligible]}")
    if not eligible:
        print("[smoke] no provider configured (.env empty)")
        return 1

    cost = CostTracker()
    adapter = RealLLMAdapter(settings=settings, cost=cost, config={"request_timeout_s": 30})

    t0 = time.time()
    text = adapter.chat(
        messages=[
            {"role": "system", "content": "You output a single JSON object only."},
            {"role": "user", "content": 'Return {"hello": "world", "ok": true}'},
        ],
        op="smoke.chat",
        max_tokens=64,
        temperature=0.0,
        json_mode=True,
    )
    dt = time.time() - t0
    print(f"[smoke] response in {dt:.2f}s: {text!r}")
    print(f"[smoke] cost summary: {cost.summary()}")

    if not text or '"hello"' not in text:
        print("[smoke] FAILED — provider did not return expected JSON")
        return 2
    print("[smoke] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
