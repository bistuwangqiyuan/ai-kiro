"""Mock moderation adapter — keyword match against `redlines.yaml` (REQ-EXT-007).

We model the real system's "OpenAI + ByteDance dual-AND" rule (design §8) by
flipping two flags from the same keyword list; M2 only needs to hard-block on
hits, so single hit -> both flags True (worst-case).
"""

from __future__ import annotations

from typing import Any


class MockModerationAdapter:
    name = "MockModerationAdapter"

    def __init__(self, *, redlines: list[str]) -> None:
        self.redlines = [r.lower() for r in redlines]

    def screen(self, payload: dict[str, Any]) -> dict[str, Any]:
        hits: list[str] = []
        for _k, v in payload.items():
            if not isinstance(v, str):
                continue
            low = v.lower()
            for rl in self.redlines:
                if rl and rl in low:
                    hits.append(rl)
                    break
        any_hit = bool(hits)
        return {
            "openai_hit": any_hit,
            "bytedance_hit": any_hit,
            "hits": hits,
        }
