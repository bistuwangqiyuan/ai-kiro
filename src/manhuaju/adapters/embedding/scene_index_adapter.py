"""Scene embedding + index adapter.

Two implementations:

1. ``MockSceneEmbedder`` — deterministic SHA-seeded random vectors;
   used in unit tests and the e2e pilot.
2. ``DashscopeSceneEmbedder`` — lazy-loaded production embedder backed by
   Dashscope ``text-embedding-v3``.

Both implement the ``SceneEmbedder`` protocol.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

import numpy as np

EMBEDDING_DIM = 768


class SceneEmbedder(Protocol):
    def embed(self, text: str) -> np.ndarray: ...

    @property
    def name(self) -> str: ...


@dataclass(frozen=True)
class MockSceneEmbedder:
    seed_offset: int = 0

    @property
    def name(self) -> str:
        return f"mock-scene-embedder-v1[+{self.seed_offset}]"

    def embed(self, text: str) -> np.ndarray:
        h = hashlib.sha256(f"{self.seed_offset}|{text}".encode()).digest()
        seed = int.from_bytes(h[:8], "big") & 0x7FFFFFFF
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else v


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity in [-1, 1]; for normalised vectors equals dot product."""

    if a.size == 0 or b.size == 0:
        return 0.0
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
