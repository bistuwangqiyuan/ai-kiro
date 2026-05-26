"""Deterministic mock pose detection adapter.

Returns a 17×3 keypoint tensor (COCO format) seeded by ``(image_path, label)``
so two calls on the same input produce identical output. Used for offline tests
and the e2e pilot.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

KEYPOINT_NAMES = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)
N_KEYPOINTS = len(KEYPOINT_NAMES)


@dataclass(frozen=True)
class PoseDetection:
    keypoints_xy: np.ndarray  # (17, 2) float
    confidences: np.ndarray  # (17,) float in [0, 1]
    detector_version: str

    def mean_confidence(self) -> float:
        return float(self.confidences.mean())


def _seeded_rng(*keys: object) -> np.random.Generator:
    h = hashlib.sha256("|".join(str(k) for k in keys).encode()).digest()
    seed = int.from_bytes(h[:8], "big") & 0x7FFFFFFF
    return np.random.default_rng(seed)


def detect(image_path: Path | str, label: str = "default") -> PoseDetection:
    """Mock detection that returns plausible keypoints anchored to a stable seed."""

    rng = _seeded_rng(str(image_path), label, "mock_openpose_v1")
    # base canvas 1024x1024
    centre = np.array([512.0, 600.0])
    spread = np.array([180.0, 280.0])
    kpts = centre + (rng.standard_normal((N_KEYPOINTS, 2)) * spread * 0.18)
    kpts = np.clip(kpts, 0.0, 1023.0)
    confs = 0.75 + 0.20 * rng.random(N_KEYPOINTS)
    return PoseDetection(
        keypoints_xy=kpts,
        confidences=confs.astype(np.float32),
        detector_version="mock-openpose-v1",
    )


def cosine_similarity(a: PoseDetection, b: PoseDetection) -> float:
    """Pose similarity via flattened keypoint cosine; returns 0..1."""

    va = a.keypoints_xy.flatten()
    vb = b.keypoints_xy.flatten()
    if va.size == 0 or vb.size == 0:
        return 0.0
    num = float(np.dot(va, vb))
    den = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if den == 0.0:
        return 0.0
    return float(np.clip(num / den, 0.0, 1.0))
