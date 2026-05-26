"""Season + dynasty → outfit subset matcher (REQ-OUT-002).

Pure deterministic mapping. The keys are taken directly from the project's
``StoryBlueprint.atmosphere`` (season ∈ {spring, summer, autumn, winter} ×
dynasty ∈ {modern, ancient_tang, ancient_song, ancient_ming, xianxia}).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Season = Literal["spring", "summer", "autumn", "winter"]
Dynasty = Literal["modern", "ancient_tang", "ancient_song", "ancient_ming", "xianxia"]


@dataclass(frozen=True)
class OutfitRecommendation:
    season: Season
    dynasty: Dynasty
    outfit_tags: tuple[str, ...]
    fabric_hint: str
    palette_hint: str


_TABLE: dict[tuple[Season, Dynasty], OutfitRecommendation] = {
    ("spring", "modern"): OutfitRecommendation("spring", "modern", ("knit_cardigan", "tencel_pleated_skirt"), "soft cotton blend", "pastel cream / pale rose"),
    ("summer", "modern"): OutfitRecommendation("summer", "modern", ("camisole_dress", "linen_short_sleeve"), "linen / chiffon", "icy mint / sky blue"),
    ("autumn", "modern"): OutfitRecommendation("autumn", "modern", ("trench_coat", "wool_skirt"), "fine wool", "rust amber / olive"),
    ("winter", "modern"): OutfitRecommendation("winter", "modern", ("down_jacket", "cashmere_scarf"), "cashmere / down", "deep navy / pearl white"),

    ("spring", "ancient_tang"): OutfitRecommendation("spring", "ancient_tang", ("ru_qun", "pibo_silk"), "silk", "peach pink / spring green"),
    ("summer", "ancient_tang"): OutfitRecommendation("summer", "ancient_tang", ("light_ruqun", "thin_silk_robe"), "thin silk", "ivory / lake blue"),
    ("autumn", "ancient_tang"): OutfitRecommendation("autumn", "ancient_tang", ("autumn_robe", "embroidered_cape"), "satin", "maple red / gold"),
    ("winter", "ancient_tang"): OutfitRecommendation("winter", "ancient_tang", ("fur_cloak", "thick_robe"), "fur lined", "winter plum / silver"),

    ("spring", "ancient_song"): OutfitRecommendation("spring", "ancient_song", ("beizi", "song_dress"), "fine cotton silk", "ink wash / lotus"),
    ("summer", "ancient_song"): OutfitRecommendation("summer", "ancient_song", ("light_beizi", "song_summer_robe"), "ramie", "celadon / pale ink"),
    ("autumn", "ancient_song"): OutfitRecommendation("autumn", "ancient_song", ("autumn_beizi", "embroidered_robe"), "wool blend", "reed brown / soft indigo"),
    ("winter", "ancient_song"): OutfitRecommendation("winter", "ancient_song", ("fur_beizi", "winter_robe"), "fur lined silk", "deep teal / silver"),

    ("spring", "ancient_ming"): OutfitRecommendation("spring", "ancient_ming", ("aoqun", "horse_face_skirt"), "embroidered silk", "azure / cherry"),
    ("summer", "ancient_ming"): OutfitRecommendation("summer", "ancient_ming", ("short_aoqun", "summer_skirt"), "thin silk", "duck egg / lotus"),
    ("autumn", "ancient_ming"): OutfitRecommendation("autumn", "ancient_ming", ("autumn_aoqun", "long_skirt"), "satin", "auburn / amber"),
    ("winter", "ancient_ming"): OutfitRecommendation("winter", "ancient_ming", ("winter_aoqun", "fur_skirt"), "fur lined satin", "midnight blue / pearl"),

    ("spring", "xianxia"): OutfitRecommendation("spring", "xianxia", ("immortal_robe_white", "feather_cape_pale"), "celestial silk", "moonlight / crystal blue"),
    ("summer", "xianxia"): OutfitRecommendation("summer", "xianxia", ("immortal_robe_light", "summer_celestial"), "starlight gauze", "lake blue / mist white"),
    ("autumn", "xianxia"): OutfitRecommendation("autumn", "xianxia", ("immortal_robe_red", "autumn_feather"), "phoenix silk", "blood red / autumn gold"),
    ("winter", "xianxia"): OutfitRecommendation("winter", "xianxia", ("snow_immortal_robe", "ice_cape"), "ice crystal silk", "ice blue / frost silver"),
}


def match(season: Season, dynasty: Dynasty) -> OutfitRecommendation:
    """Deterministic mapping; raises ``KeyError`` on unknown combos."""

    if (season, dynasty) not in _TABLE:
        raise KeyError(f"unknown (season,dynasty) combo: ({season!r}, {dynasty!r})")
    return _TABLE[(season, dynasty)]


def coverage() -> float:
    """Return fraction of the (Season × Dynasty) Cartesian product covered."""

    seasons = ("spring", "summer", "autumn", "winter")
    dynasties = ("modern", "ancient_tang", "ancient_song", "ancient_ming", "xianxia")
    total = len(seasons) * len(dynasties)
    covered = sum(1 for s in seasons for d in dynasties if (s, d) in _TABLE)
    return covered / total
