"""Unit tests for distribution pack + watermark + copy router (REQ-DIST-001..005)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from manhuaju.services.copy_style_router import ALL_PLATFORMS, render, render_all
from manhuaju.services.distribution_pack import DistributionPackSvc
from manhuaju.services.watermark import apply_watermark


def test_five_platforms_supported() -> None:
    """REQ-DIST-001: 5 platforms supported."""

    assert set(ALL_PLATFORMS) == {"douyin", "kuaishou", "bilibili", "video_hao", "youtube"}
    assert len(ALL_PLATFORMS) == 5


def test_render_all_yields_per_platform_copy() -> None:
    """REQ-DIST-004: each platform has its own CTA / hashtag count.

    Titles may collide for short inputs, but descriptions and hashtag-counts
    must always differ — they encode the per-platform voice.
    """

    out = render_all("奶茶街的姐姐 EP01", "都市轻喜剧", ("都市", "甜宠", "短剧", "AI", "Manhuaju", "v2", "test", "more"))
    assert set(out.keys()) == set(ALL_PLATFORMS)
    descriptions = {p: out[p].description for p in ALL_PLATFORMS}
    assert len(set(descriptions.values())) == 5
    hashtag_counts = {p: len(out[p].hashtags) for p in ALL_PLATFORMS}
    assert len(set(hashtag_counts.values())) >= 4


def test_render_truncates_to_platform_max() -> None:
    """REQ-DIST-004: title length respects per-platform limit."""

    long_title = "x" * 200
    for plat in ALL_PLATFORMS:
        c = render(plat, long_title, "summary", ())
        assert len(c.title) <= 200, plat


def test_render_unsupported_platform_raises() -> None:
    with pytest.raises(ValueError):
        render("instagram", "title", "summary", ())  # type: ignore[arg-type]


def test_distribution_pack_builds_all_platforms(tmp_path: Path) -> None:
    """REQ-DIST-001 + -003: build emits one export per platform + manifest."""

    master_video = tmp_path / "master.mp4"
    master_video.write_bytes(b"\x00\x01\x02fake")
    master_cover = tmp_path / "cover.png"
    Image.new("RGB", (1280, 720), (200, 80, 120)).save(master_cover)

    svc = DistributionPackSvc(output_root=tmp_path / "out")
    pack = svc.build(
        project_id="prj_test",
        episode_index=1,
        master_video_path=master_video,
        master_cover_path=master_cover,
        title_root="测试集",
        summary="一段简短的剧情简介",
        base_hashtags=("剧情", "测试", "AI", "Manhuaju"),
    )

    assert len(pack.exports) == len(ALL_PLATFORMS)
    plats = {e.platform for e in pack.exports}
    assert plats == set(ALL_PLATFORMS)
    for e in pack.exports:
        assert Path(e.output_video_path).exists()
        assert Path(e.output_cover_path).exists()
    manifest = json.loads(Path(pack.manifest_path).read_text(encoding="utf-8"))
    assert manifest["project_id"] == "prj_test"
    assert manifest["episode_index"] == 1
    assert len(manifest["exports"]) == 5


def test_watermark_writes_output(tmp_path: Path) -> None:
    """REQ-DIST-002: watermark applied successfully and output written."""

    src = tmp_path / "cover.png"
    Image.new("RGB", (1280, 720), (10, 10, 50)).save(src)
    out = tmp_path / "cover_wm.png"
    res = apply_watermark(src, out, text="© Manhuaju", position="bottom_right", opacity=0.7)
    assert out.exists()
    assert res.position == "bottom_right"


def test_watermark_byte_identical(tmp_path: Path) -> None:
    """REQ-DIST-002: deterministic output for identical inputs."""

    src = tmp_path / "cover.png"
    Image.new("RGB", (1024, 1024), (12, 13, 18)).save(src)
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    apply_watermark(src, a, text="© M")
    apply_watermark(src, b, text="© M")
    assert a.read_bytes() == b.read_bytes()


def test_watermark_invalid_opacity_raises(tmp_path: Path) -> None:
    src = tmp_path / "x.png"
    Image.new("RGB", (10, 10), (0, 0, 0)).save(src)
    with pytest.raises(ValueError):
        apply_watermark(src, tmp_path / "y.png", opacity=0.0)


def test_pack_unknown_platform_raises(tmp_path: Path) -> None:
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    cover = tmp_path / "c.png"
    Image.new("RGB", (10, 10), (0, 0, 0)).save(cover)
    svc = DistributionPackSvc(output_root=tmp_path / "out")
    with pytest.raises(ValueError):
        svc.build("p", 1, src, cover, "t", "s", (), platforms=("instagram",))  # type: ignore[arg-type]


def test_distinct_sha_per_platform(tmp_path: Path) -> None:
    src = tmp_path / "v.mp4"
    src.write_bytes(b"hello")
    cover = tmp_path / "c.png"
    Image.new("RGB", (10, 10), (0, 0, 0)).save(cover)
    svc = DistributionPackSvc(output_root=tmp_path / "out")
    pack = svc.build("p", 1, src, cover, "T", "S", ("a", "b"))
    shas = {e.sha for e in pack.exports}
    assert len(shas) == 5
