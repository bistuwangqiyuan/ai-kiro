"""Unit tests for the action library + pose adapter (REQ-ACT-001..006)."""

from __future__ import annotations

import pytest

from manhuaju.adapters.pose.mock_openpose_adapter import N_KEYPOINTS, cosine_similarity, detect
from manhuaju.adapters.pose.real_dwpose_adapter import detect as real_detect
from manhuaju.services.action_library import (
    MIN_DETECTOR_CONFIDENCE,
    REUSE_SIMILARITY_THRESHOLD,
    ActionLibrarySvc,
)


@pytest.fixture(scope="module")
def lib() -> ActionLibrarySvc:
    return ActionLibrarySvc.load()


def test_action_lib_at_least_12(lib: ActionLibrarySvc) -> None:
    """REQ-ACT-001: ≥ 12 base poses configured."""

    assert lib.has_minimum_base_poses(12)
    assert len(lib.catalogue) >= 12


def test_mock_pose_deterministic() -> None:
    """Mock detection is byte-identical for same inputs."""

    a = detect("imgs/x.png", "stand")
    b = detect("imgs/x.png", "stand")
    assert (a.keypoints_xy == b.keypoints_xy).all()
    assert a.detector_version == b.detector_version == "mock-openpose-v1"
    assert a.keypoints_xy.shape == (N_KEYPOINTS, 2)


def test_mock_pose_different_labels_differ() -> None:
    a = detect("imgs/x.png", "stand")
    b = detect("imgs/x.png", "run")
    assert not (a.keypoints_xy == b.keypoints_xy).all()


def test_pose_provenance_required(lib: ActionLibrarySvc) -> None:
    """REQ-ACT-003: persist origin + detector version on every cache."""

    pose = lib.detect_and_cache("imgs/x.png", "stand", "char-1", "ep1-shot-001")
    assert pose is not None
    assert pose.detector_version == "mock-openpose-v1"
    assert pose.source_shot_id == "ep1-shot-001"
    assert len(pose.pose_tensor_sha) == 16


def test_action_cache_hit_after_first_detection(lib: ActionLibrarySvc) -> None:
    """REQ-ACT-002: same image+action → cache hit."""

    lib.detect_and_cache("imgs/y.png", "walk", "char-2", "ep1-shot-002")
    reused = lib.try_reuse("imgs/y.png", "walk", "char-2")
    assert reused is not None
    assert reused.action_id == "walk"


def test_action_cache_miss_when_uncached(lib: ActionLibrarySvc) -> None:
    fresh = ActionLibrarySvc.load()
    out = fresh.try_reuse("imgs/z.png", "run", "char-3")
    assert out is None
    assert fresh.cache_hits == 0
    assert fresh.cache_misses == 1


def test_pose_degraded_when_low_confidence(monkeypatch) -> None:
    """REQ-ACT-005: detector confidence < 0.6 → return None for graceful degradation."""

    class Faux:
        keypoints_xy = detect("img/dummy", "stand").keypoints_xy
        confidences = (detect("img/dummy", "stand").confidences * 0.0) + 0.3
        detector_version = "mock-openpose-v1"

        def mean_confidence(self) -> float:
            return float(self.confidences.mean())

    lib = ActionLibrarySvc.load()
    lib.detector = lambda p, a: Faux()  # type: ignore[assignment]
    out = lib.detect_and_cache("img/x", "stand", "c1", "ep1-shot-001")
    assert out is None


def test_real_adapter_raises_without_ckpt(monkeypatch) -> None:
    """The real DWPose adapter should fail-fast without checkpoint, allowing fallback."""

    monkeypatch.delenv("MANHUAJU_DWPOSE_CKPT", raising=False)
    with pytest.raises(RuntimeError):
        real_detect("img/x", "stand")


def test_custom_action_added(lib: ActionLibrarySvc) -> None:
    """REQ-ACT-004: user-uploaded action extends catalogue."""

    initial = len(lib.catalogue)
    e = lib.add_custom_action("flying_kick", "飞踢", "腾空飞踢，气势如虹", pacing="fast")
    assert "flying_kick" in lib.catalogue
    assert e.zh == "飞踢"
    assert len(lib.catalogue) == initial + 1


def test_custom_action_duplicate_rejected(lib: ActionLibrarySvc) -> None:
    with pytest.raises(ValueError):
        lib.add_custom_action("stand", "x", "y")


def test_threshold_constants_anchored() -> None:
    """REQ-ACT-002 / -005 anchors must match the spec."""

    assert REUSE_SIMILARITY_THRESHOLD == 0.90
    assert MIN_DETECTOR_CONFIDENCE == 0.60


def test_pose_self_cosine_is_one() -> None:
    a = detect("img/y", "stand")
    assert cosine_similarity(a, a) == pytest.approx(1.0, abs=1e-6)


def test_action_prompt_segment(lib: ActionLibrarySvc) -> None:
    e = lib.catalogue["stand"]
    seg_zh = e.to_prompt_segment("zh")
    seg_en = e.to_prompt_segment("en")
    assert "[动作:" in seg_zh
    assert "[ACTION:stand]" in seg_en
