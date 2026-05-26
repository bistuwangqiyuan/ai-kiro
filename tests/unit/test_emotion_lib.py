"""Unit tests for emotion library + injection (REQ-EMO-001..007)."""

from __future__ import annotations

import pytest

from manhuaju.services.emotion_injection import (
    auto_resolve_emotion,
    emotion_token_present,
    inject,
)
from manhuaju.services.emotion_library import (
    ARCFACE_MIN_DEFAULT,
    EmotionLibrarySvc,
)


@pytest.fixture(scope="module")
def lib() -> EmotionLibrarySvc:
    return EmotionLibrarySvc.load()


def test_emotion_lib_at_least_7(lib: EmotionLibrarySvc) -> None:
    """REQ-EMO-001: ≥ 7 base emotions configured."""

    assert len(lib.catalogue) >= 7


def test_resolve_tag_zh_alias(lib: EmotionLibrarySvc) -> None:
    assert lib.resolve_tag("喜") == "joy"
    assert lib.resolve_tag("惊讶") == "surprise"
    assert lib.resolve_tag("anger") == "anger"


def test_resolve_unknown_raises(lib: EmotionLibrarySvc) -> None:
    with pytest.raises(KeyError):
        lib.resolve_tag("nonexistent_emotion")


def test_emotion_arcface_ge_094_promotes(lib: EmotionLibrarySvc) -> None:
    """REQ-EMO-002: variant with ArcFace ≥ 0.94 is promoted."""

    v = lib.add_variant("char-1", "joy", ref_paths=("a.png",), arcface_score=0.95)
    assert v.promoted is True
    assert v.passes_gate()
    assert ("char-1", "joy") in lib.variants


def test_emotion_arcface_below_threshold_rejected(lib: EmotionLibrarySvc) -> None:
    """REQ-EMO-002: below threshold the variant is *not* persisted."""

    v = lib.add_variant("char-2", "anger", ref_paths=("b.png",), arcface_score=0.90)
    assert v.promoted is False
    assert ("char-2", "anger") not in lib.variants


def test_emotion_token_in_prompt_when_dialogue(lib: EmotionLibrarySvc) -> None:
    """REQ-EMO-003: dialogue triggers emotion clause injection."""

    pb = {"clauses": ["close-up shot"], "dialogue": "她笑得格外开心，眼角都弯了起来"}
    out = inject(pb, lib)
    assert emotion_token_present(out)
    assert out["emotion_tag"] == "joy"


def test_explicit_tag_overrides_dialogue(lib: EmotionLibrarySvc) -> None:
    pb = {"clauses": [], "dialogue": "随便一句"}
    out = inject(pb, lib, explicit_tag="anger")
    assert out["emotion_tag"] == "anger"


def test_custom_emotion_added(lib: EmotionLibrarySvc) -> None:
    """REQ-EMO-004: custom emotion can be added."""

    e = lib.add_custom_emotion("smug", "得意", "嘴角斜挑，眯眼")
    assert "smug" in lib.catalogue
    assert e.zh == "得意"


def test_custom_emotion_duplicate_rejected(lib: EmotionLibrarySvc) -> None:
    with pytest.raises(ValueError):
        lib.add_custom_emotion("joy", "x", "y")


def test_default_arcface_threshold_is_anchored() -> None:
    """REQ-EMO-002 anchor: 0.94 matches whitepaper consistency lead lower CI."""

    assert ARCFACE_MIN_DEFAULT == 0.94


def test_auto_resolve_falls_back_when_no_keywords(lib: EmotionLibrarySvc) -> None:
    assert auto_resolve_emotion("", lib) == "thoughtful"


def test_fallback_calm(lib: EmotionLibrarySvc) -> None:
    """REQ-EMO-007: degrade-to-calm baseline."""

    e = lib.fallback_calm()
    assert e.tag in ("calm", "thoughtful") or e is next(iter(lib.catalogue.values()))


def test_seven_per_character_count(lib: EmotionLibrarySvc) -> None:
    """REQ-EMO-001: at least 7 promoted variants needed for completeness."""

    char_id = "lead-001"
    for tag, score in zip(lib.all_tags()[:7], [0.95] * 7, strict=True):
        lib.add_variant(char_id, tag, ref_paths=(f"{tag}.png",), arcface_score=score)
    assert lib.has_at_least_seven_for(char_id)
