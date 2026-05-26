"""Outfit change with state-machine + ArcFace identity gate (REQ-OUT-001..006).

The state machine forbids non-sensical transitions (e.g. swimwear → wedding gown
mid-shot without an explicit ``sequence_break``). The ArcFace gate ensures
identity is preserved across outfits.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from manhuaju.services.season_dynasty_matcher import (
    Dynasty,
    OutfitRecommendation,
    Season,
    match,
)

#: REQ-OUT-003 anchor: identical to emotion ArcFace gate.
ARCFACE_MIN = 0.94

OutfitContext = Literal["casual", "formal", "battle", "intimate", "sleep", "transit", "ceremony"]


@dataclass(frozen=True)
class OutfitVariant:
    outfit_id: str
    char_id: str
    season: Season
    dynasty: Dynasty
    context: OutfitContext
    fabric: str
    palette: str
    arcface_score: float
    sha: str
    ref_paths: tuple[str, ...] = ()
    promoted: bool = False

    def passes_gate(self, threshold: float = ARCFACE_MIN) -> bool:
        return self.arcface_score >= threshold


# Allowed transitions: (from_context, to_context). Same context always allowed.
_ALLOWED_TRANSITIONS: set[tuple[OutfitContext, OutfitContext]] = {
    ("casual", "formal"),
    ("casual", "transit"),
    ("casual", "battle"),
    ("casual", "sleep"),
    ("casual", "intimate"),
    ("formal", "casual"),
    ("formal", "ceremony"),
    ("formal", "transit"),
    ("transit", "casual"),
    ("transit", "formal"),
    ("transit", "battle"),
    ("battle", "casual"),
    ("battle", "transit"),
    ("sleep", "casual"),
    ("sleep", "intimate"),
    ("intimate", "casual"),
    ("intimate", "sleep"),
    ("ceremony", "formal"),
    ("ceremony", "casual"),
}


@dataclass
class OutfitChangeSvc:
    variants: dict[str, OutfitVariant] = field(default_factory=dict)
    transition_log: list[tuple[str, str, OutfitContext, OutfitContext]] = field(default_factory=list)

    def is_allowed(self, from_ctx: OutfitContext, to_ctx: OutfitContext) -> bool:
        if from_ctx == to_ctx:
            return True
        return (from_ctx, to_ctx) in _ALLOWED_TRANSITIONS

    def plan_outfit(
        self,
        char_id: str,
        season: Season,
        dynasty: Dynasty,
        context: OutfitContext,
    ) -> OutfitRecommendation:
        """REQ-OUT-002: project season+dynasty → recommended outfit subset."""

        rec = match(season, dynasty)
        # Apply context-specific palette adjustments.
        if context == "battle":
            return OutfitRecommendation(
                season=rec.season,
                dynasty=rec.dynasty,
                outfit_tags=rec.outfit_tags,
                fabric_hint=rec.fabric_hint + " (reinforced)",
                palette_hint=rec.palette_hint + " · darkened for battle",
            )
        if context == "ceremony":
            return OutfitRecommendation(
                season=rec.season,
                dynasty=rec.dynasty,
                outfit_tags=rec.outfit_tags,
                fabric_hint=rec.fabric_hint + " · embroidered",
                palette_hint=rec.palette_hint + " · ceremonial accents",
            )
        return rec

    def commit_variant(
        self,
        char_id: str,
        from_ctx: OutfitContext,
        to_ctx: OutfitContext,
        season: Season,
        dynasty: Dynasty,
        ref_paths: tuple[str, ...],
        arcface_score: float,
        threshold: float = ARCFACE_MIN,
    ) -> OutfitVariant:
        """REQ-OUT-001 + -003: state-machine guard + ArcFace gate."""

        if not self.is_allowed(from_ctx, to_ctx):
            raise ValueError(f"outfit_state_violation: {from_ctx!r} -> {to_ctx!r}")
        rec = self.plan_outfit(char_id, season, dynasty, to_ctx)
        outfit_id = "+".join(rec.outfit_tags)
        sha = hashlib.sha256(
            f"{char_id}|{outfit_id}|{','.join(ref_paths)}|{arcface_score:.4f}".encode()
        ).hexdigest()[:16]
        variant = OutfitVariant(
            outfit_id=outfit_id,
            char_id=char_id,
            season=season,
            dynasty=dynasty,
            context=to_ctx,
            fabric=rec.fabric_hint,
            palette=rec.palette_hint,
            arcface_score=arcface_score,
            sha=sha,
            ref_paths=ref_paths,
            promoted=arcface_score >= threshold,
        )
        if variant.promoted:
            self.variants[f"{char_id}|{outfit_id}|{to_ctx}"] = variant
            self.transition_log.append((char_id, outfit_id, from_ctx, to_ctx))
        return variant

    def has_ref_for(self, char_id: str, outfit_id: str, context: OutfitContext) -> bool:
        """REQ-OUT-004: enforce reference image availability before first use."""

        return f"{char_id}|{outfit_id}|{context}" in self.variants
