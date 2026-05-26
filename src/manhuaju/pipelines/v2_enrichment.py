"""V2 enrichment passes around the existing Manhuaju agent flow.

The core 4-step Volcengine pipeline (``ManhuajuAgentPipeline``) remains the
authoritative orchestrator for novel→video. This module adds *pre-* and
*post-flight* passes that integrate the 11 new v2.0 services without modifying
the legacy pipeline contract:

* **Pre-flight** (before stage 1):
    1. ``ModeRouter``   — resolves Simple/Pro defaults.
    2. ``TemplateEngine`` — optionally swap in a viral genre template.
    3. ``SceneLibrarySvc.preload`` — warm scene index for reuse decisions.
    4. ``EmotionLibrarySvc.load`` + ``ActionLibrarySvc.load``.
    5. ``OutfitChangeSvc`` — initial empty (filled per shot).

* **Post-flight** (after stage 4 of every episode):
    6. ``align`` — snap shot transitions to BGM beats.
    7. ``apply_watermark`` — stamp covers.
    8. ``DistributionPackSvc.build`` — multi-platform export.

The dependency direction stays ``adapters → services → pipelines``
(no service imports back into pipelines), keeping ``import-linter`` happy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from manhuaju.services.action_library import ActionLibrarySvc
from manhuaju.services.auto_cut import ShotPlan, align
from manhuaju.services.distribution_pack import DistributionPack, DistributionPackSvc
from manhuaju.services.emotion_library import EmotionLibrarySvc
from manhuaju.services.music_alignment import detect_beats
from manhuaju.services.outfit_change import OutfitChangeSvc
from manhuaju.services.scene_library import SceneLibrarySvc
from manhuaju.services.style_transfer import StyleTransferSvc
from manhuaju.services.template_engine import RenderedTemplate, TemplateEngine
from manhuaju.services.watermark import apply_watermark

log = logging.getLogger(__name__)


@dataclass
class V2Bundle:
    """Holds the new v2 services for the duration of a project run.

    Mode routing happens at the **api** layer (one layer above pipelines per
    ``import-linter``); callers must pass an already-resolved payload here.
    """

    emotion_lib: EmotionLibrarySvc = field(default_factory=EmotionLibrarySvc.load)
    action_lib: ActionLibrarySvc = field(default_factory=ActionLibrarySvc.load)
    outfit_svc: OutfitChangeSvc = field(default_factory=OutfitChangeSvc)
    scene_lib: SceneLibrarySvc = field(default_factory=SceneLibrarySvc)
    template_engine: TemplateEngine = field(default_factory=TemplateEngine)
    style_transfer: StyleTransferSvc = field(default_factory=StyleTransferSvc)
    distribution: DistributionPackSvc = field(default_factory=DistributionPackSvc)


@dataclass
class PreflightResult:
    resolved_payload: dict[str, Any]
    rendered_template: RenderedTemplate | None
    bundle: V2Bundle


def preflight(
    resolved_payload: dict[str, Any],
    *,
    template_id: str | None = None,
    template_variables: dict[str, Any] | None = None,
    bundle: V2Bundle | None = None,
) -> PreflightResult:
    """REQ-TPL-*: optionally render a viral genre template after mode routing.

    ``resolved_payload`` must already be the output of
    ``manhuaju.api.mode_router.ModeRouter.route(mode, payload)`` — keeping the
    api layer above pipelines per ``import-linter``.
    """

    bundle = bundle or V2Bundle()
    rendered: RenderedTemplate | None = None
    payload = dict(resolved_payload)
    if template_id:
        rendered = bundle.template_engine.render(
            template_id,
            template_variables or {},
            episode_count=payload.get("episode_count"),
        )
        for k, v in rendered.defaults.items():
            payload.setdefault(k, v)
    return PreflightResult(
        resolved_payload=payload,
        rendered_template=rendered,
        bundle=bundle,
    )


@dataclass
class PostflightResult:
    aligned_shots: list[Any]
    distribution: DistributionPack | None
    cover_watermarked: str | None


def postflight(
    project_id: str,
    episode_index: int,
    shot_plan: list[ShotPlan],
    bgm_path: Path | str,
    bgm_duration_s: float,
    *,
    master_video_path: Path | str | None = None,
    master_cover_path: Path | str | None = None,
    title_root: str = "Episode",
    summary: str = "",
    base_hashtags: tuple[str, ...] = (),
    bundle: V2Bundle | None = None,
    output_root: Path | None = None,
) -> PostflightResult:
    """REQ-AC-* + REQ-DIST-*: BGM-align + watermark + multi-platform distribution."""

    bundle = bundle or V2Bundle()
    if output_root:
        bundle.distribution.output_root = output_root

    track = detect_beats(bgm_path, duration_s=bgm_duration_s)
    aligned = align(shot_plan, track)

    pack: DistributionPack | None = None
    cover_wm: str | None = None
    if master_video_path and master_cover_path:
        wm_path = Path(master_cover_path).with_name(Path(master_cover_path).stem + ".wm.png")
        try:
            apply_watermark(master_cover_path, wm_path)
            cover_wm = str(wm_path)
        except Exception as e:  # noqa: BLE001
            log.warning("watermark failed: %s", e)
            cover_wm = None
        try:
            pack = bundle.distribution.build(
                project_id=project_id,
                episode_index=episode_index,
                master_video_path=master_video_path,
                master_cover_path=cover_wm or master_cover_path,
                title_root=title_root,
                summary=summary,
                base_hashtags=base_hashtags or ("剧情", "AI", "Manhuaju"),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("distribution pack build failed: %s", e)
            pack = None

    return PostflightResult(aligned_shots=aligned, distribution=pack, cover_watermarked=cover_wm)
