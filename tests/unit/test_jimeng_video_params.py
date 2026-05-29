"""Gate the Jimeng video param builder + req_key detection (real-render fix)."""

from __future__ import annotations

from manhuaju.adapters.render.real_xiaoyunque_adapter import (
    _is_jimeng_req_key,
    _jimeng_video_params,
)


def test_is_jimeng_req_key() -> None:
    assert _is_jimeng_req_key("jimeng_t2v_v30")
    assert _is_jimeng_req_key("jimeng_i2v_first_v30")
    assert not _is_jimeng_req_key("skylark_video_agent_v2_with_ref")
    assert not _is_jimeng_req_key("")


def test_jimeng_params_minimal_schema() -> None:
    """Jimeng must receive only {req_key, prompt, aspect_ratio, frames, seed}.

    Skylark-only fields (character_references etc.) and ``duration`` would be
    rejected with 50200 and silently degrade the shot to a mock placeholder.
    """
    p = _jimeng_video_params(
        req_key="jimeng_t2v_v30",
        prompt="荀彧劝曹操迎献帝, 真人写实",
        aspect_ratio="16:9",
        duration_s=5,
        fps=24,
        seed=20260516,
    )
    assert set(p.keys()) == {"req_key", "prompt", "aspect_ratio", "frames", "seed"}
    assert "duration" not in p
    assert "character_references" not in p
    assert p["frames"] == 121  # ~5s @ 24fps


def test_jimeng_params_snaps_to_10s_for_long_shots() -> None:
    p = _jimeng_video_params(
        req_key="jimeng_t2v_v30",
        prompt="x",
        aspect_ratio="16:9",
        duration_s=10,
        fps=24,
        seed=1,
    )
    assert p["frames"] == 241  # ~10s @ 24fps


def test_jimeng_params_seed_masked() -> None:
    p = _jimeng_video_params(
        req_key="jimeng_t2v_v30",
        prompt="x",
        aspect_ratio="9:16",
        duration_s=5,
        fps=24,
        seed=-1,
    )
    assert p["seed"] >= 0
