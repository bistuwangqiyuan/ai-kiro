"""Map browser / mode-router payloads to project-create dicts (REQ-MODE-*)."""

from __future__ import annotations

from typing import Any

from manhuaju.api.mode_router import ModeRouter

TEMPLATE_IDS = frozenset({"cdrama_classic", "sweet_pet", "xianxia_epic"})
GENRE_FROM_TEMPLATE = {
    "cdrama_classic": "modern",
    "sweet_pet": "sweet_pet",
    "xianxia_epic": "xianxia",
}


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

    return {
        "novel_text": novel_text[:50_000],
        "seed": int(data.get("seed", 20260516)),
        "episode_count": int(data.get("episode_count", 3)),
        "style_preset_id": str(data.get("style_preset_id", "cinematic_2d_v1")),
        "genre": genre,
        "target_audience": str(data.get("target_audience", "general")),
        "episode_duration_s": int(data.get("episode_duration_s", 75)),
        "template_id": str(template_id) if template_id else None,
        "platforms": list(platforms),
    }
