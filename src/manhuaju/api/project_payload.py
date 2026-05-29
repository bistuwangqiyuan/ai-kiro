"""Map browser / mode-router payloads to project-create dicts (REQ-MODE-*)."""

from __future__ import annotations

from typing import Any

import yaml

from manhuaju.api.mode_router import ModeRouter
from manhuaju.utils.paths import config_dir

TEMPLATE_IDS = frozenset({"cdrama_classic", "sweet_pet", "xianxia_epic"})
GENRE_FROM_TEMPLATE = {
    "cdrama_classic": "modern",
    "sweet_pet": "sweet_pet",
    "xianxia_epic": "xianxia",
}


def style_preset_defaults(preset_id: str) -> dict[str, Any]:
    """Read resolution / aspect_ratio / visual_style from config/style-presets.yaml."""
    path = config_dir() / "style-presets.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    block = data.get(preset_id) if isinstance(data, dict) else None
    return dict(block) if isinstance(block, dict) else {}


def resolve_project_create(
    raw: dict[str, Any],
    *,
    router: ModeRouter | None = None,
) -> dict[str, Any]:
    """Accept console / simple / pro JSON; return fields for ``ProjectCreateRequest``."""

    data = dict(raw)
    mode = data.get("mode")
    if mode in ("simple", "pro"):
        router = router or ModeRouter.load()
        data = router.route(mode, data)  # type: ignore[arg-type]

    data.pop("_mode", None)
    data.pop("_mode_resolved_keys", None)

    platforms = data.get("platforms") or data.get("distribution_platforms") or [
        "douyin",
        "kuaishou",
        "weixin",
    ]
    if isinstance(platforms, str):
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]

    novel_text = str(data.get("novel_text") or "").strip()
    title = str(data.get("title") or "").strip()
    if len(novel_text) < 10:
        prefix = f"{title}。" if title else ""
        novel_text = f"{prefix}{novel_text}".strip()
    if len(novel_text) < 10:
        novel_text = (
            (title or "漫剧作品")
            + "：她从未想过，重生之后第一个见到的，竟是那个她以为已经死了的男人……"
        )

    genre = str(data.get("genre") or "ancient")
    template_id = data.get("template_id")
    if genre in TEMPLATE_IDS:
        template_id = str(template_id or genre)
        genre = GENRE_FROM_TEMPLATE.get(genre, "modern")

    style_preset_id = str(data.get("style_preset_id", "cinematic_2d_v1"))
    preset = style_preset_defaults(style_preset_id)
    resolution = str(data.get("resolution") or preset.get("resolution") or "720p")
    aspect_ratio = str(data.get("aspect_ratio") or preset.get("aspect_ratio") or "16:9")
    visual_style = str(data.get("visual_style") or preset.get("visual_style") or "")

    return {
        "novel_text": novel_text[:50_000],
        "seed": int(data.get("seed", 20260516)),
        # Default to 1 shortest episode so anonymous users + the deploy-loop
        # gates can finish a real generation inside the FaaS request budget
        # (~30 min) without burning multiple episodes' worth of credits per
        # smoke run. Pro mode lets users override.
        "episode_count": int(data.get("episode_count", 1)),
        "style_preset_id": style_preset_id,
        "genre": genre,
        "target_audience": str(data.get("target_audience", "general")),
        "episode_duration_s": int(data.get("episode_duration_s", 30)),
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "visual_style": visual_style,
        "template_id": str(template_id) if template_id else None,
        "platforms": list(platforms),
    }
