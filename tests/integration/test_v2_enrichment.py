"""Integration tests for the v2 pre-/post-flight enrichment passes."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from manhuaju.api.mode_router import ModeRouter
from manhuaju.pipelines.v2_enrichment import (
    PreflightResult,
    V2Bundle,
    postflight,
    preflight,
)
from manhuaju.services.auto_cut import ShotPlan


def test_preflight_simple_mode_with_template() -> None:
    """Api layer (ModeRouter) → pipelines layer (preflight) chain."""

    router = ModeRouter.load()
    resolved = router.route("simple", {"novel_text": "x", "title": "T"})
    res = preflight(
        resolved,
        template_id="cdrama_classic",
        template_variables={
            "protagonist_name": "苏小晚",
            "setting_city": "上海",
            "dramatic_hook": "She never saw it coming",
        },
    )
    assert isinstance(res, PreflightResult)
    assert res.rendered_template is not None
    assert res.rendered_template.template_id == "cdrama_classic"
    # Simple-mode default is now "1 shortest episode" so the deploy-loop
    # gate can finish a real render inside the FaaS timeout.
    assert res.resolved_payload["episode_count"] == 1


def test_preflight_pro_mode_no_template() -> None:
    router = ModeRouter.load()
    resolved = router.route("pro", {"novel_text": "x", "render_tier": "H"})
    res = preflight(resolved)
    assert res.rendered_template is None
    assert res.resolved_payload["render_tier"] == "H"


def test_postflight_alignment_only(tmp_path: Path) -> None:
    """Postflight runs alignment without distribution when no master files given."""

    shots = [
        ShotPlan(shot_id="s1", in_s=0.0, out_s=2.05),
        ShotPlan(shot_id="s2", in_s=2.05, out_s=4.10),
        ShotPlan(shot_id="s3", in_s=4.10, out_s=6.10),
    ]
    bgm = tmp_path / "bgm.mp3"
    bgm.write_bytes(b"fakebgm")
    res = postflight(
        project_id="prj_test",
        episode_index=1,
        shot_plan=shots,
        bgm_path=bgm,
        bgm_duration_s=10.0,
    )
    assert len(res.aligned_shots) == 3
    assert res.distribution is None
    assert res.cover_watermarked is None


def test_postflight_full_path(tmp_path: Path) -> None:
    """End-to-end postflight with watermark + distribution."""

    bundle = V2Bundle()
    bgm = tmp_path / "bgm.mp3"
    bgm.write_bytes(b"x")
    master_video = tmp_path / "master.mp4"
    master_video.write_bytes(b"\x00\x01\x02")
    master_cover = tmp_path / "cover.png"
    Image.new("RGB", (1280, 720), (200, 80, 120)).save(master_cover)

    shots = [
        ShotPlan(shot_id="s1", in_s=0.0, out_s=2.0),
        ShotPlan(shot_id="s2", in_s=2.0, out_s=4.0),
    ]
    res = postflight(
        project_id="prj_test",
        episode_index=1,
        shot_plan=shots,
        bgm_path=bgm,
        bgm_duration_s=4.0,
        master_video_path=master_video,
        master_cover_path=master_cover,
        title_root="测试",
        summary="测试简介",
        base_hashtags=("剧情", "测试"),
        bundle=bundle,
        output_root=tmp_path / "out",
    )
    assert res.distribution is not None
    assert len(res.distribution.exports) == 5
    assert res.cover_watermarked is not None
    assert Path(res.cover_watermarked).exists()


def test_v2_bundle_carries_seven_services() -> None:
    """V2Bundle wires up the 7 stateful services (mode-router lives in api layer)."""

    b = V2Bundle()
    assert b.emotion_lib is not None
    assert b.action_lib is not None
    assert b.outfit_svc is not None
    assert b.scene_lib is not None
    assert b.template_engine is not None
    assert b.style_transfer is not None
    assert b.distribution is not None
