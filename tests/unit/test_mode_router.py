"""Unit tests for the dual-mode entry router (REQ-MODE-001..006)."""

from __future__ import annotations

import pytest

from manhuaju.api.mode_router import ModeRouter


@pytest.fixture(scope="module")
def router() -> ModeRouter:
    return ModeRouter.load()


def test_loads_both_presets(router: ModeRouter) -> None:
    """REQ-MODE-001: both modes are configured."""

    assert "simple" in router.presets
    assert "pro" in router.presets


def test_simple_mode_locks_advanced_params(router: ModeRouter) -> None:
    """REQ-MODE-001: simple mode hides ≥ 80% of advanced parameters."""

    locked = router.presets["simple"].locked_params
    assert len(locked) >= 10
    # at least these critical advanced params must be locked
    for must_lock in ("render_tier", "moderation_layers", "scene_reuse_threshold"):
        assert must_lock in locked, must_lock


def test_pro_mode_unlocks_everything(router: ModeRouter) -> None:
    """REQ-MODE-001: pro exposes 100%."""

    assert router.presets["pro"].locked_params == ()


def test_simple_preset_byte_identical(router: ModeRouter) -> None:
    """REQ-MODE-003: identical inputs in `simple` resolve to identical configs."""

    a = router.route("simple", {"title": "x", "novel_text": "y"})
    b = router.route("simple", {"title": "x", "novel_text": "y"})
    assert a == b
    assert a["render_tier"] == "M"
    # Default = 1 shortest episode (so anonymous + smoke runs finish a real
    # render inside the 30 min FaaS timeout). Pro mode lets users override.
    assert a["episode_count"] == 1


def test_locked_param_returns_409(router: ModeRouter) -> None:
    """REQ-MODE-004: setting a locked param in simple mode is forbidden."""

    with pytest.raises(ValueError, match="mode_locked"):
        router.route("simple", {"render_tier": "H", "novel_text": "z"})


def test_pro_overrides_propagate(router: ModeRouter) -> None:
    """Pro mode passes user overrides through unchanged."""

    out = router.route("pro", {"render_tier": "H", "episode_count": 10})
    assert out["render_tier"] == "H"
    assert out["episode_count"] == 10


def test_mode_resolved_keys_recorded(router: ModeRouter) -> None:
    """REQ-MODE-005: provenance records which keys came from which source."""

    out = router.route("simple", {"novel_text": "x"})
    assert "_mode" in out and out["_mode"] == "simple"
    assert "_mode_resolved_keys" in out
    assert "render_tier" in out["_mode_resolved_keys"]


def test_unknown_mode_raises(router: ModeRouter) -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        router.route("expert", {})  # type: ignore[arg-type]


def test_mode_switch_preserves_artefacts(router: ModeRouter) -> None:
    """REQ-MODE-002: switching modes mid-project never loses data.

    Resolution: identical user fields produce identical merged values for both
    modes when those fields are not locked.
    """

    payload_pro = {"novel_text": "x", "title": "T"}
    pro_resolved = router.route("pro", payload_pro)
    simple_resolved = router.route("simple", payload_pro)
    # User fields preserved in both
    assert pro_resolved["novel_text"] == simple_resolved["novel_text"]
    assert pro_resolved["title"] == simple_resolved["title"]
