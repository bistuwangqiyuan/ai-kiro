"""Deterministic mock style-transfer adapter.

Returns a fake ``StyleTransferResult`` with an ArcFace score derived
deterministically from input ``(input_path, target_style, identity_lock)``.
Used for offline tests and the e2e pilot.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class StyleTransferResult:
    output_path: str
    target_style: str
    identity_locked: bool
    arcface_score: float
    style_score: float
    adapter_version: str
    prompt_sha: str


def _seeded_score(*keys: object, low: float, high: float) -> float:
    h = hashlib.sha256("|".join(str(k) for k in keys).encode()).digest()
    n = int.from_bytes(h[:6], "big") / float(1 << 48)
    return low + (high - low) * n


def transfer(
    input_path: str,
    target_style: str,
    identity_lock: bool = True,
    output_path: str | None = None,
) -> StyleTransferResult:
    output = output_path or f"{input_path}.{target_style}.png"
    # When identity_lock=True, ArcFace score is biased high; otherwise it can drift.
    if identity_lock:
        arc = _seeded_score(input_path, target_style, "id_locked", low=0.93, high=0.99)
    else:
        arc = _seeded_score(input_path, target_style, "id_free", low=0.80, high=0.95)
    style = _seeded_score(input_path, target_style, "style", low=0.65, high=0.92)
    sha = hashlib.sha256(f"{input_path}|{target_style}|{identity_lock}".encode()).hexdigest()[:16]
    return StyleTransferResult(
        output_path=output,
        target_style=target_style,
        identity_locked=identity_lock,
        arcface_score=arc,
        style_score=style,
        adapter_version="mock-styletx-v1",
        prompt_sha=sha,
    )
