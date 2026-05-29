"""Gate the Ark Seedance --flag param suffix (real-render fix)."""

from __future__ import annotations

from manhuaju.adapters.render.real_seedance_adapter import RealSeedanceAdapter


def test_ark_param_suffix_defaults() -> None:
    s = RealSeedanceAdapter._ark_param_suffix(
        {"resolution": "720p", "duration_s": 5, "aspect_ratio": "16:9"}
    )
    assert "--resolution 720p" in s
    assert "--duration 5" in s
    assert "--ratio 16:9" in s


def test_ark_param_suffix_clamps_duration_and_maps_res() -> None:
    s = RealSeedanceAdapter._ark_param_suffix({"resolution": "1080p", "duration_s": 99})
    assert "--resolution 1080p" in s
    assert "--duration 12" in s  # clamped to Seedance max
    assert "--ratio 16:9" in s   # default when not provided


def test_ark_param_suffix_480_and_min_duration() -> None:
    s = RealSeedanceAdapter._ark_param_suffix({"resolution": "480p", "duration_s": 1})
    assert "--resolution 480p" in s
    assert "--duration 3" in s   # clamped to Seedance min
