"""Cost & latency tracker for live API calls.

The tracker is *append-only* and thread-safe (within asyncio single-loop usage).
It records per-call telemetry as canonical JSON and computes pilot KPIs:

- total RMB spent
- p50/p95 latency per provider
- success / fallback / error counts
- per-episode budget burn

A single tracker instance is owned by AgentContext for an entire pipeline run.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostEntry:
    timestamp_s: float
    provider: str
    operation: str  # "llm", "video.submit", "video.poll", "tts", "embedding", "moderation"
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_s: float = 0.0
    rmb: float = 0.0
    success: bool = True
    error_class: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# Indicative pricing in RMB. Use config/cost.yaml `live_pricing` for production.
DEFAULT_PRICING_RMB: dict[str, dict[str, float]] = {
    "groq.llm": {"prompt_per_1k": 0.0, "completion_per_1k": 0.0},
    "deepseek.llm": {"prompt_per_1k": 0.0014, "completion_per_1k": 0.0028},
    "moonshot.llm": {"prompt_per_1k": 0.012, "completion_per_1k": 0.012},
    "glm.llm": {"prompt_per_1k": 0.001, "completion_per_1k": 0.001},
    "volcengine.llm": {"prompt_per_1k": 0.0008, "completion_per_1k": 0.002},
    "mistral.llm": {"prompt_per_1k": 0.014, "completion_per_1k": 0.042},
    "dashscope.llm": {"prompt_per_1k": 0.004, "completion_per_1k": 0.012},
    "volcengine.video": {"per_second": 0.7},  # Seedance ~ ¥0.7/s
    "dashscope.video": {"per_second": 0.5},  # WanX 2.1 t2v turbo
    "dashscope.tts": {"per_kchar": 0.10},  # CosyVoice ~ ¥0.10/1k chars
    "dashscope.embedding": {"per_1k": 0.0007},
}


class CostTracker:
    def __init__(self, pricing: dict[str, dict[str, float]] | None = None) -> None:
        # RLock so internal methods that already hold the lock can call
        # self.summary() without deadlocking (e.g. to_dict → summary).
        self._lock = threading.RLock()
        self._entries: list[CostEntry] = []
        self._pricing = pricing or DEFAULT_PRICING_RMB

    def estimate_llm(self, provider: str, in_tok: int, out_tok: int) -> float:
        p = self._pricing.get(f"{provider}.llm", {})
        return (in_tok / 1000.0) * p.get("prompt_per_1k", 0.0) + (out_tok / 1000.0) * p.get(
            "completion_per_1k", 0.0
        )

    def estimate_video(self, provider: str, seconds: float) -> float:
        p = self._pricing.get(f"{provider}.video", {})
        return float(seconds) * p.get("per_second", 0.0)

    def estimate_tts(self, provider: str, n_chars: int) -> float:
        p = self._pricing.get(f"{provider}.tts", {})
        return (n_chars / 1000.0) * p.get("per_kchar", 0.0)

    def estimate_embedding(self, provider: str, n_tokens: int) -> float:
        p = self._pricing.get(f"{provider}.embedding", {})
        return (n_tokens / 1000.0) * p.get("per_1k", 0.0)

    def record(self, entry: CostEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    @property
    def total_rmb(self) -> float:
        with self._lock:
            return round(sum(e.rmb for e in self._entries if e.success), 4)

    @property
    def total_duration_s(self) -> float:
        with self._lock:
            return round(sum(e.duration_s for e in self._entries), 3)

    def by_op(self, op: str) -> list[CostEntry]:
        with self._lock:
            return [e for e in self._entries if e.operation == op]

    def summary(self) -> dict[str, Any]:
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return {"calls": 0, "rmb": 0.0, "duration_s": 0.0, "providers": {}}

        per_prov: dict[str, dict[str, Any]] = {}
        for e in entries:
            slot = per_prov.setdefault(
                e.provider,
                {"calls": 0, "rmb": 0.0, "errors": 0, "latencies": []},
            )
            slot["calls"] += 1
            slot["rmb"] += e.rmb
            slot["latencies"].append(e.duration_s)
            if not e.success:
                slot["errors"] += 1

        for slot in per_prov.values():
            lat = sorted(slot.pop("latencies"))
            n = len(lat)
            slot["p50_s"] = round(lat[n // 2], 3) if n else 0.0
            slot["p95_s"] = round(lat[max(0, int(n * 0.95) - 1)], 3) if n else 0.0
            slot["rmb"] = round(slot["rmb"], 4)

        total_rmb = round(sum(e.rmb for e in entries if e.success), 4)
        total_dur = round(sum(e.duration_s for e in entries), 3)
        return {
            "calls": len(entries),
            "rmb": total_rmb,
            "duration_s": total_dur,
            "providers": per_prov,
        }

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "summary": self.summary(),
                "entries": [
                    {
                        "ts": e.timestamp_s,
                        "provider": e.provider,
                        "operation": e.operation,
                        "model": e.model,
                        "in_tok": e.input_tokens,
                        "out_tok": e.output_tokens,
                        "duration_s": round(e.duration_s, 3),
                        "rmb": round(e.rmb, 4),
                        "ok": e.success,
                        "error": e.error_class,
                        "extra": e.extra,
                    }
                    for e in self._entries
                ],
            }


def now_s() -> float:
    return time.monotonic()
