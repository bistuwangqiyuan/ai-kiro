"""Unit tests for transmedia ingest + keyframe extractor (REQ-TM-001..006)."""

from __future__ import annotations

import pytest

from manhuaju.services.keyframe_extractor import (
    DEFAULT_KEYFRAMES_PER_SECOND,
    extract_from_comic_pages,
    extract_from_video,
)
from manhuaju.services.transmedia_ingest import TransmediaIngestSvc


def test_kf_per_second_anchor() -> None:
    """REQ-TM-002 anchor: default 1 keyframe/sec for video."""

    assert DEFAULT_KEYFRAMES_PER_SECOND == 1.0


def test_video_keyframe_count_matches_duration() -> None:
    kfs = extract_from_video("clip.mp4", duration_s=10.0, fps=1.0)
    assert len(kfs) == 10
    assert kfs[0].timestamp_s == 0.0
    assert kfs[-1].timestamp_s == 9.0


def test_video_keyframe_higher_fps_more_frames() -> None:
    kfs = extract_from_video("clip.mp4", duration_s=10.0, fps=2.0)
    assert len(kfs) == 20


def test_video_extractor_validates_duration() -> None:
    with pytest.raises(ValueError):
        extract_from_video("clip.mp4", duration_s=0.0)


def test_comic_keyframes_one_per_panel() -> None:
    kfs = extract_from_comic_pages(["p1.png", "p2.png", "p3.png"], panels_per_page=4)
    assert len(kfs) == 12
    assert all(k.source_kind == "comic" for k in kfs)


def test_ingest_video_returns_segment() -> None:
    svc = TransmediaIngestSvc()
    seg = svc.ingest_video("clip.mp4", duration_s=5.0, license_kind="licensed", rights_holder="StudioX")
    assert seg.source_kind == "video"
    assert seg.keyframe_count == 5
    assert svc.can_publish(seg)


def test_ingest_comic_returns_segment() -> None:
    svc = TransmediaIngestSvc()
    seg = svc.ingest_comic(["p1.png", "p2.png"], rights_holder="OrigArtist", license_kind="licensed")
    assert seg.source_kind == "comic"
    assert seg.keyframe_count >= 2


def test_publish_blocked_for_fan_made() -> None:
    """REQ-TM-005: fan-made content cannot be published without explicit license."""

    svc = TransmediaIngestSvc()
    seg = svc.ingest_video("clip.mp4", duration_s=3.0, license_kind="fan_made")
    assert not svc.can_publish(seg)


def test_publish_blocked_for_unknown_license() -> None:
    svc = TransmediaIngestSvc()
    seg = svc.ingest_comic(["x.png"], license_kind="unknown")
    assert not svc.can_publish(seg)


def test_disable_license_check_allows_publish() -> None:
    svc = TransmediaIngestSvc(license_required_for_publish=False)
    seg = svc.ingest_video("clip.mp4", duration_s=2.0, license_kind="fan_made")
    assert svc.can_publish(seg)


def test_empty_comic_input_raises() -> None:
    svc = TransmediaIngestSvc()
    with pytest.raises(ValueError):
        svc.ingest_comic([])


def test_segment_fingerprint_unique() -> None:
    svc = TransmediaIngestSvc()
    seg1 = svc.ingest_video("clipA.mp4", duration_s=2.0)
    seg2 = svc.ingest_video("clipB.mp4", duration_s=2.0)
    assert seg1.fingerprint_sha != seg2.fingerprint_sha


def test_segment_byte_identical() -> None:
    """REQ-TM-002: same input → identical fingerprint (deterministic)."""

    svc1 = TransmediaIngestSvc()
    svc2 = TransmediaIngestSvc()
    a = svc1.ingest_video("clip.mp4", duration_s=4.0)
    b = svc2.ingest_video("clip.mp4", duration_s=4.0)
    assert a.fingerprint_sha == b.fingerprint_sha
    assert a.keyframes[0].sha == b.keyframes[0].sha
