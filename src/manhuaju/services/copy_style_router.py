"""Per-platform copywriting style router (REQ-DIST-004).

Each platform has its own preferred title format, hashtag count, emoji density,
and CTA voice. This service produces ready-to-publish title/description/tags
for each of the 5 supported platforms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Platform = Literal["douyin", "kuaishou", "bilibili", "video_hao", "youtube"]
ALL_PLATFORMS: tuple[Platform, ...] = ("douyin", "kuaishou", "bilibili", "video_hao", "youtube")


@dataclass(frozen=True)
class PlatformStyle:
    name: Platform
    title_max_len: int
    hashtag_count: int
    emoji_density: float
    cta_template: str
    description_max_len: int


_STYLES: dict[Platform, PlatformStyle] = {
    "douyin": PlatformStyle("douyin", 22, 5, 0.20, "👇评论区告诉我你的想法！", 80),
    "kuaishou": PlatformStyle("kuaishou", 30, 4, 0.15, "老铁双击关注不迷路！", 100),
    "bilibili": PlatformStyle("bilibili", 80, 3, 0.05, "三连支持up主，下集见！", 250),
    "video_hao": PlatformStyle("video_hao", 60, 2, 0.02, "点赞收藏，与你共鸣。", 200),
    "youtube": PlatformStyle("youtube", 100, 8, 0.02, "Subscribe for more episodes!", 1500),
}


@dataclass(frozen=True)
class PlatformCopy:
    platform: Platform
    title: str
    description: str
    hashtags: tuple[str, ...]


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    if max_len <= 1:
        return s[:max_len]
    return s[: max_len - 1] + "…"


def _emoji_layer(density: float, base: str = "🎬✨🌙🔥💞") -> str:
    if density <= 0:
        return ""
    n = max(1, int(round(len(base) * density)))
    return base[:n]


def render(
    platform: Platform,
    title_root: str,
    summary: str,
    base_hashtags: tuple[str, ...],
) -> PlatformCopy:
    """Produce platform-tailored title, description, and hashtags."""

    if platform not in _STYLES:
        raise ValueError(f"unsupported platform: {platform!r}")
    style = _STYLES[platform]
    emoji = _emoji_layer(style.emoji_density)
    title = _truncate(f"{emoji}{title_root}", style.title_max_len)
    desc_body = f"{summary} {style.cta_template}".strip()
    description = _truncate(desc_body, style.description_max_len)
    hashtags = tuple(f"#{tag}" for tag in base_hashtags[: style.hashtag_count])
    return PlatformCopy(
        platform=platform,
        title=title,
        description=description,
        hashtags=hashtags,
    )


def render_all(
    title_root: str,
    summary: str,
    base_hashtags: tuple[str, ...],
) -> dict[Platform, PlatformCopy]:
    return {p: render(p, title_root, summary, base_hashtags) for p in ALL_PLATFORMS}
