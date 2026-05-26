"""Unit tests for outfit change + season/dynasty matcher (REQ-OUT-001..006)."""

from __future__ import annotations

import pytest

from manhuaju.services.outfit_change import ARCFACE_MIN, OutfitChangeSvc
from manhuaju.services.season_dynasty_matcher import coverage, match


def test_season_dynasty_match_coverage_ge_095() -> None:
    """REQ-OUT-002: ≥ 95% coverage of (season × dynasty) Cartesian product."""

    assert coverage() >= 0.95


def test_match_returns_deterministic_recommendation() -> None:
    a = match("spring", "ancient_tang")
    b = match("spring", "ancient_tang")
    assert a == b
    assert "ru_qun" in a.outfit_tags


def test_match_unknown_combo_raises() -> None:
    with pytest.raises(KeyError):
        match("spring", "alien")  # type: ignore[arg-type]


@pytest.fixture
def svc() -> OutfitChangeSvc:
    return OutfitChangeSvc()


def test_outfit_state_machine_rejects_illegal(svc: OutfitChangeSvc) -> None:
    """REQ-OUT-001: illegal transitions raise."""

    with pytest.raises(ValueError, match="outfit_state_violation"):
        svc.commit_variant(
            "char-1",
            from_ctx="ceremony",
            to_ctx="battle",
            season="autumn",
            dynasty="xianxia",
            ref_paths=("a.png",),
            arcface_score=0.96,
        )


def test_outfit_arcface_ge_094_promotes(svc: OutfitChangeSvc) -> None:
    """REQ-OUT-003: variant with ArcFace ≥ 0.94 is promoted."""

    v = svc.commit_variant(
        "char-1",
        from_ctx="casual",
        to_ctx="formal",
        season="spring",
        dynasty="modern",
        ref_paths=("a.png",),
        arcface_score=0.95,
    )
    assert v.promoted is True
    assert v.passes_gate()


def test_outfit_arcface_below_threshold_rejected(svc: OutfitChangeSvc) -> None:
    v = svc.commit_variant(
        "char-2",
        from_ctx="casual",
        to_ctx="formal",
        season="spring",
        dynasty="modern",
        ref_paths=("a.png",),
        arcface_score=0.91,
    )
    assert v.promoted is False
    assert not svc.has_ref_for("char-2", v.outfit_id, "formal")


def test_missing_outfit_ref_failfast(svc: OutfitChangeSvc) -> None:
    """REQ-OUT-004: outfit needs a ref image before first use."""

    assert not svc.has_ref_for("char-x", "non-existent-outfit", "casual")


def test_outfit_id_in_metadata(svc: OutfitChangeSvc) -> None:
    """REQ-OUT-005: outfit_id and SHA persisted on the variant."""

    v = svc.commit_variant(
        "char-3",
        from_ctx="casual",
        to_ctx="transit",
        season="winter",
        dynasty="ancient_tang",
        ref_paths=("a.png", "b.png"),
        arcface_score=0.95,
    )
    assert v.outfit_id
    assert len(v.sha) == 16
    assert v.fabric.startswith("fur lined")


def test_battle_context_alters_palette(svc: OutfitChangeSvc) -> None:
    rec = svc.plan_outfit("char-x", "autumn", "xianxia", "battle")
    assert "darkened for battle" in rec.palette_hint


def test_ceremony_context_adds_embroidery(svc: OutfitChangeSvc) -> None:
    rec = svc.plan_outfit("char-x", "spring", "ancient_tang", "ceremony")
    assert "embroidered" in rec.fabric_hint


def test_arcface_threshold_anchor() -> None:
    """REQ-OUT-003 anchor."""

    assert ARCFACE_MIN == 0.94


def test_same_context_transition_allowed(svc: OutfitChangeSvc) -> None:
    """Same context → same context is always allowed (idempotent)."""

    v = svc.commit_variant(
        "char-y",
        from_ctx="casual",
        to_ctx="casual",
        season="summer",
        dynasty="modern",
        ref_paths=("c.png",),
        arcface_score=0.95,
    )
    assert v.promoted
