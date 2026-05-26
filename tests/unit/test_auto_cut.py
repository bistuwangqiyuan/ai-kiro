"""Unit tests for music alignment + auto-cut (REQ-AC-001..006)."""

from __future__ import annotations

import pytest

from manhuaju.services.auto_cut import (
    DEFAULT_SNAP_DRIFT_S,
    MAX_SHOT_GROWTH_RATIO,
    MAX_TOTAL_DRIFT_S,
    MIN_SHOT_SHRINK_RATIO,
    ShotPlan,
    align,
    total_duration_drift,
)
from manhuaju.services.music_alignment import (
    MockBeatDetector,
    detect_beats,
    snap_to_beats,
)


def test_constants_anchored() -> None:
    """REQ-AC-002 / -003 / -004 anchors."""

    assert DEFAULT_SNAP_DRIFT_S == pytest.approx(0.20)
    assert MAX_TOTAL_DRIFT_S == 0.5
    assert MAX_SHOT_GROWTH_RATIO == 1.25
    assert MIN_SHOT_SHRINK_RATIO == 0.50


def test_mock_beat_detector_deterministic() -> None:
    a = detect_beats("song.mp3", duration_s=30.0)
    b = detect_beats("song.mp3", duration_s=30.0)
    assert a.bpm == b.bpm
    assert a.beats_s == b.beats_s


def test_beats_cover_duration() -> None:
    track = detect_beats("song.mp3", duration_s=10.0)
    assert track.beats_s[0] == 0.0
    assert track.beats_s[-1] <= 10.0
    assert track.bpm > 0


def test_downbeats_subset() -> None:
    track = detect_beats("song.mp3", duration_s=20.0)
    downs = track.downbeats(every=4)
    assert len(downs) == (len(track.beats_s) + 3) // 4


def test_snap_within_drift_window() -> None:
    """REQ-AC-002: events within drift window snap."""

    beats = (0.0, 1.0, 2.0, 3.0)
    snapped = snap_to_beats([0.05, 1.15, 2.30], beats, max_drift=0.20)
    assert snapped == [0.0, 1.0, 2.30]  # 2.30 outside drift → kept


def test_align_simple_case() -> None:
    """Three shots align to nearest beat without violating per-shot bounds."""

    shots = [
        ShotPlan(shot_id="s1", in_s=0.0, out_s=2.05),
        ShotPlan(shot_id="s2", in_s=2.05, out_s=4.10),
        ShotPlan(shot_id="s3", in_s=4.10, out_s=6.10),
    ]
    track = MockBeatDetector().detect("song.mp3", duration_s=10.0)
    aligned = align(shots, track, snap_drift_s=0.50)
    assert len(aligned) == 3
    drift = total_duration_drift(shots, aligned)
    assert abs(drift) <= MAX_TOTAL_DRIFT_S


def test_align_preserves_per_shot_bounds() -> None:
    """REQ-AC-004: snapping that would violate bounds is rejected."""

    shots = [
        ShotPlan(shot_id="s1", in_s=0.0, out_s=0.5),  # very short
        ShotPlan(shot_id="s2", in_s=0.5, out_s=10.0),
    ]
    # Beats far away from 0.5 → snapping would explode shot s1
    track = MockBeatDetector().detect("song.mp3", duration_s=10.0)
    aligned = align(shots, track, snap_drift_s=5.0)
    s1 = aligned[0]
    assert s1.duration <= MAX_SHOT_GROWTH_RATIO * 0.5 + 1e-6
    assert s1.duration >= MIN_SHOT_SHRINK_RATIO * 0.5 - 1e-6


def test_align_marks_unaligned_when_outside_drift() -> None:
    """When transition is far from any beat, alignment is skipped."""

    shots = [
        ShotPlan(shot_id="s1", in_s=0.0, out_s=1.51),
        ShotPlan(shot_id="s2", in_s=1.51, out_s=3.02),
    ]
    track = MockBeatDetector().detect("song.mp3", duration_s=5.0)
    aligned = align(shots, track, snap_drift_s=0.05)  # very tight window
    # at least s1 is unaligned (its out_s likely not close enough to a beat)
    assert any(not a.aligned for a in aligned)


def test_align_empty_shots_returns_empty() -> None:
    track = MockBeatDetector().detect("song.mp3", duration_s=5.0)
    assert align([], track) == []


def test_total_duration_drift_within_threshold() -> None:
    """REQ-AC-003: aggregate drift never exceeds ±0.5s."""

    shots = [ShotPlan(shot_id=f"s{i}", in_s=i * 2.0, out_s=(i + 1) * 2.0) for i in range(10)]
    track = MockBeatDetector().detect("song.mp3", duration_s=20.0)
    aligned = align(shots, track, snap_drift_s=0.20)
    assert abs(total_duration_drift(shots, aligned)) <= MAX_TOTAL_DRIFT_S


def test_align_last_shot_keeps_out_s() -> None:
    """The final shot's out_s never changes (= episode end)."""

    shots = [
        ShotPlan(shot_id="s1", in_s=0.0, out_s=2.0),
        ShotPlan(shot_id="s2", in_s=2.0, out_s=4.0),
    ]
    track = MockBeatDetector().detect("song.mp3", duration_s=4.0)
    aligned = align(shots, track, snap_drift_s=0.30)
    assert aligned[-1].out_s == 4.0
