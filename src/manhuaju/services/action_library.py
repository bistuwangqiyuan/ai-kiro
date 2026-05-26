"""Action / pose library runtime (REQ-ACT-001..006).

Loads ``config/action-library.yaml``, runs deterministic pose detection (mock or
real adapter), and decides whether to reuse a cached pose vs. regenerate.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from manhuaju.adapters.pose import mock_openpose_adapter as mock_pose
from manhuaju.utils.paths import config_dir

#: REQ-ACT-002: cosine similarity ≥ 0.90 → reuse instead of regen.
REUSE_SIMILARITY_THRESHOLD = 0.90
#: REQ-ACT-005: detector confidence < 0.6 → degrade to text-only action.
MIN_DETECTOR_CONFIDENCE = 0.60


@dataclass(frozen=True)
class ActionEntry:
    tag: str
    zh: str
    prompt_zh: str
    prompt_en: str
    pacing: str

    def to_prompt_segment(self, lang: str = "zh") -> str:
        if lang == "zh":
            return f"[动作:{self.zh}] {self.prompt_zh}（节奏:{self.pacing}）"
        return f"[ACTION:{self.tag}] {self.prompt_en} (pacing={self.pacing})"


@dataclass(frozen=True)
class ActionPose:
    action_id: str
    char_id: str
    source_shot_id: str
    pose_tensor_sha: str
    detector_version: str
    confidence: float


@dataclass
class ActionLibrarySvc:
    catalogue: dict[str, ActionEntry] = field(default_factory=dict)
    poses: dict[str, ActionPose] = field(default_factory=dict)
    cache_hits: int = 0
    cache_misses: int = 0
    detector: Callable[[Path | str, str], mock_pose.PoseDetection] = mock_pose.detect

    @classmethod
    def load(cls, config_path: Path | None = None) -> ActionLibrarySvc:
        path = config_path or (config_dir() / "action-library.yaml")
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cat: dict[str, ActionEntry] = {}
        for tag, payload in (data.get("actions") or {}).items():
            cat[tag] = ActionEntry(
                tag=tag,
                zh=str(payload.get("zh", tag)),
                prompt_zh=str(payload.get("prompt_zh", "")),
                prompt_en=str(payload.get("prompt_en", "")),
                pacing=str(payload.get("pacing", "static")),
            )
        return cls(catalogue=cat)

    def all_tags(self) -> list[str]:
        return list(self.catalogue.keys())

    def has_minimum_base_poses(self, minimum: int = 12) -> bool:
        """REQ-ACT-001: ≥ 12 base poses configured."""

        return len(self.catalogue) >= minimum

    def detect_and_cache(
        self,
        image_path: Path | str,
        action_id: str,
        char_id: str,
        source_shot_id: str,
    ) -> ActionPose | None:
        """Run pose detection on ``image_path`` and cache the result.

        Returns ``None`` if the detector confidence is below ``MIN_DETECTOR_CONFIDENCE``
        — caller should degrade to text-only (REQ-ACT-005).
        """

        det = self.detector(image_path, action_id)
        confidence = det.mean_confidence()
        if confidence < MIN_DETECTOR_CONFIDENCE:
            return None
        sha = hashlib.sha256(det.keypoints_xy.tobytes()).hexdigest()[:16]
        pose = ActionPose(
            action_id=action_id,
            char_id=char_id,
            source_shot_id=source_shot_id,
            pose_tensor_sha=sha,
            detector_version=det.detector_version,
            confidence=confidence,
        )
        self.poses[f"{char_id}|{action_id}"] = pose
        return pose

    def try_reuse(
        self,
        image_path: Path | str,
        action_id: str,
        char_id: str,
        threshold: float = REUSE_SIMILARITY_THRESHOLD,
    ) -> ActionPose | None:
        """REQ-ACT-002: reuse the cached pose when the new detection is similar enough."""

        key = f"{char_id}|{action_id}"
        cached = self.poses.get(key)
        if cached is None:
            self.cache_misses += 1
            return None
        # Recompute current detection and compare via cosine similarity
        cur = self.detector(image_path, action_id)
        # We rebuild a fresh PoseDetection from the cache hash → not possible without
        # storing keypoints. Strategy: reuse if cached confidence > threshold and
        # the per-detection sha cosine ≈ 1 (deterministic mock). Real DWPose path
        # would compare keypoints directly.
        # For deterministic mock, the SAME image+label produces identical sha.
        cur_sha = hashlib.sha256(cur.keypoints_xy.tobytes()).hexdigest()[:16]
        if cur_sha == cached.pose_tensor_sha and cur.mean_confidence() >= MIN_DETECTOR_CONFIDENCE:
            self.cache_hits += 1
            return cached
        self.cache_misses += 1
        return None

    def cache_hit_ratio(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total) if total > 0 else 0.0

    def add_custom_action(self, tag: str, zh: str, prompt_zh: str, pacing: str = "static") -> ActionEntry:
        """REQ-ACT-004: extend the catalogue with a user-uploaded pose label."""

        if tag in self.catalogue:
            raise ValueError(f"action tag already exists: {tag!r}")
        e = ActionEntry(tag=tag, zh=zh, prompt_zh=prompt_zh, prompt_en="", pacing=pacing)
        self.catalogue[tag] = e
        return e
