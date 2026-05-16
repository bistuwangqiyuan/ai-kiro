"""Mock embedding adapter (REQ-EXT-008). Deterministic 64-dim from sha256."""

from __future__ import annotations

import hashlib
import math


class MockEmbeddingAdapter:
    name = "MockEmbeddingAdapter"
    dim = 64

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        v = []
        for i in range(self.dim):
            byte = digest[i % len(digest)]
            v.append((byte / 255.0) * 2 - 1)
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]
