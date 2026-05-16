"""Deterministic seed derivation (REQ-IN-004 / REQ-RO-007 / REQ-PILOT-010)."""

from __future__ import annotations

import hashlib
from typing import Any


def _h(*parts: Any) -> int:
    s = "|".join(str(p) for p in parts)
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False) & 0x7FFFFFFFFFFFFFFF


def project_seed(seed: int) -> int:
    return _h("project", seed)


def episode_seed(project_seed_v: int, episode_id: str) -> int:
    return _h("episode", project_seed_v, episode_id)


def shot_seed(episode_seed_v: int, shot_id: str, retry_count: int = 0) -> int:
    return _h("shot", episode_seed_v, shot_id, retry_count)


def reference_seed(bible_sha: str, view_id: str) -> int:
    return _h("ref", bible_sha, view_id)


def derive_bool(s: int, prob: float) -> bool:
    """Deterministic bernoulli with given p in [0,1]."""
    f = (s % 1_000_000) / 1_000_000.0
    return f < prob
