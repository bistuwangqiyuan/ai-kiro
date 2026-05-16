"""Real DashScope text-embedding-v3 adapter (M3).

Returns L2-normalised float vectors (default dim 1024 for text-embedding-v3).
On any error degrades to the mock adapter so pipeline never blocks on
embeddings (used only by ContinuityChecker proxy and a few QA paths).
"""

from __future__ import annotations

import math
import time
from typing import Any

import httpx

from manhuaju.adapters.embedding.mock_embedding_adapter import MockEmbeddingAdapter
from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s
from manhuaju.core.provider_settings import ProviderSettings

_API_URL = (
    "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
)


class RealDashScopeEmbeddingAdapter:
    name = "RealDashScopeEmbeddingAdapter"
    provider = "dashscope_text_embedding_v3"
    dim = 1024

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        cost: CostTracker,
        config: dict[str, Any] | None = None,
        mock_fallback: MockEmbeddingAdapter | None = None,
    ) -> None:
        self._settings = settings
        self._cost = cost
        self._cfg = config or {}
        self.mock_fallback = mock_fallback
        self._model = self._cfg.get("model", "text-embedding-v3")
        self._timeout = float(self._cfg.get("request_timeout_s", 20))

    def embed(self, text: str) -> list[float]:
        if not self._settings.dashscope_key:
            return self._fallback(text)

        body = {"model": self._model, "input": text[:2048] or " "}
        headers = {
            "Authorization": f"Bearer {self._settings.dashscope_key}",
            "Content-Type": "application/json",
        }
        t0 = now_s()
        try:
            with httpx.Client(timeout=self._timeout) as client:
                r = client.post(_API_URL, headers=headers, json=body)
        except (httpx.HTTPError, OSError) as e:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider="dashscope",
                    operation="embedding.embed",
                    model=self._model,
                    duration_s=now_s() - t0,
                    success=False,
                    error_class=type(e).__name__,
                )
            )
            return self._fallback(text)

        duration = now_s() - t0
        if r.status_code != 200:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider="dashscope",
                    operation="embedding.embed",
                    model=self._model,
                    duration_s=duration,
                    success=False,
                    error_class=f"HTTP {r.status_code}",
                )
            )
            return self._fallback(text)

        data = r.json()
        try:
            vec = list(data["data"][0]["embedding"])
        except (KeyError, IndexError, TypeError):
            return self._fallback(text)
        usage = data.get("usage") or {}
        in_tok = int(usage.get("total_tokens", 0) or 0)
        rmb = self._cost.estimate_embedding("dashscope", in_tok or len(text) // 3)
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider="dashscope",
                operation="embedding.embed",
                model=self._model,
                input_tokens=in_tok,
                duration_s=duration,
                rmb=rmb,
                success=True,
            )
        )
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [float(x) / norm for x in vec]

    def _fallback(self, text: str) -> list[float]:
        if self.mock_fallback is None:
            return MockEmbeddingAdapter().embed(text)
        return self.mock_fallback.embed(text)
