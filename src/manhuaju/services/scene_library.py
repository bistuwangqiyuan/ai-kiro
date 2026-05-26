"""Scene library + reuse decision (REQ-SCN-001..006).

Stores scene records, embeds their descriptions, and decides reuse vs.
regenerate when a new scene description arrives. Top-k retrieval by cosine
similarity; the cutoff threshold is anchored to the whitepaper
``scene_reuse.scene_reuse_threshold = 0.85``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from manhuaju.adapters.embedding.scene_index_adapter import (
    MockSceneEmbedder,
    SceneEmbedder,
    cosine,
)

#: REQ-SCN-002 anchor — 0.85 from `data/computed/scene_reuse.json::scene_reuse_threshold`.
REUSE_THRESHOLD = 0.85

ShotScale = Literal["close", "medium", "wide"]


@dataclass(frozen=True)
class SceneEmbedding:
    scene_id: str
    description: str
    embedding: np.ndarray
    palette_hash: str
    available_scales: tuple[ShotScale, ...] = ("close", "medium", "wide")
    asset_paths: tuple[str, ...] = ()
    reuse_count: int = 0


@dataclass
class ReuseDecision:
    reuse: bool
    matched_scene_id: str | None
    similarity: float
    scale: ShotScale


@dataclass
class SceneLibrarySvc:
    embedder: SceneEmbedder = field(default_factory=lambda: MockSceneEmbedder())
    scenes: dict[str, SceneEmbedding] = field(default_factory=dict)
    reuse_log: list[ReuseDecision] = field(default_factory=list)

    def add_scene(
        self,
        scene_id: str,
        description: str,
        asset_paths: tuple[str, ...] = (),
        available_scales: tuple[ShotScale, ...] = ("close", "medium", "wide"),
    ) -> SceneEmbedding:
        if scene_id in self.scenes:
            raise ValueError(f"scene already exists: {scene_id!r}")
        emb = self.embedder.embed(description)
        palette_hash = hashlib.sha256(description.encode()).hexdigest()[:12]
        rec = SceneEmbedding(
            scene_id=scene_id,
            description=description,
            embedding=emb,
            palette_hash=palette_hash,
            available_scales=available_scales,
            asset_paths=asset_paths,
        )
        self.scenes[scene_id] = rec
        return rec

    def query(self, description: str, k: int = 3) -> list[tuple[SceneEmbedding, float]]:
        """Top-k similarity retrieval, descending."""

        if not self.scenes:
            return []
        target = self.embedder.embed(description)
        ranked = [(rec, cosine(rec.embedding, target)) for rec in self.scenes.values()]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:k]

    def decide_reuse(
        self,
        description: str,
        scale: ShotScale = "medium",
        threshold: float = REUSE_THRESHOLD,
    ) -> ReuseDecision:
        """REQ-SCN-002: similarity ≥ threshold and scale supported → reuse."""

        candidates = self.query(description, k=1)
        if not candidates:
            d = ReuseDecision(reuse=False, matched_scene_id=None, similarity=0.0, scale=scale)
            self.reuse_log.append(d)
            return d
        best, sim = candidates[0]
        scale_ok = scale in best.available_scales
        decision = ReuseDecision(
            reuse=(sim >= threshold and scale_ok),
            matched_scene_id=best.scene_id if (sim >= threshold and scale_ok) else None,
            similarity=sim,
            scale=scale,
        )
        if decision.reuse:
            object.__setattr__(best, "reuse_count", best.reuse_count + 1)
        self.reuse_log.append(decision)
        return decision

    def reuse_rate(self) -> float:
        """REQ-SCN-005 anchor: pipeline-wide reuse rate."""

        if not self.reuse_log:
            return 0.0
        hits = sum(1 for d in self.reuse_log if d.reuse)
        return hits / len(self.reuse_log)

    def total_assets(self) -> int:
        return sum(len(s.asset_paths) for s in self.scenes.values())
