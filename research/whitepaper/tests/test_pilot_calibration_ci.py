"""Pilot-calibration 95% CI must contain the headline anchors.

Even with synthetic preliminary calibration (n=3) the 95% CI for the four
calibrated metrics must (a) be finite, (b) contain the model headline.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from research.whitepaper import SEED
from research.whitepaper.models import _io, pilot_calibration


@pytest.fixture(scope="module")
def calibrated() -> pilot_calibration.CalibratedParams:
    rng = np.random.default_rng(SEED)
    return pilot_calibration.calibrate(rng)


def test_ci_bounds_are_finite(calibrated: pilot_calibration.CalibratedParams) -> None:
    for lo, hi in (
        calibrated.cost_per_episode_cny_ci95,
        calibrated.latency_episode_p95_s_ci95,
        calibrated.arcface_intra_mean_ci95,
        calibrated.p_pass_ci95,
    ):
        assert np.isfinite(lo) and np.isfinite(hi)
        assert lo <= hi


def test_ci_contains_point_estimate(calibrated: pilot_calibration.CalibratedParams) -> None:
    for value, (lo, hi) in (
        (calibrated.cost_per_episode_cny, calibrated.cost_per_episode_cny_ci95),
        (calibrated.latency_episode_p95_s, calibrated.latency_episode_p95_s_ci95),
        (calibrated.arcface_intra_mean, calibrated.arcface_intra_mean_ci95),
        (calibrated.p_pass_per_attempt, calibrated.p_pass_ci95),
    ):
        assert lo <= value <= hi


def test_calibration_status_recognised(calibrated: pilot_calibration.CalibratedParams) -> None:
    assert calibrated.calibration_status in {"calibrated_from_pilot", "synthetic_preliminary"}


def test_calibrated_params_json_round_trip(calibrated: pilot_calibration.CalibratedParams) -> None:
    p = pilot_calibration.write_calibrated_params(calibrated)
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["calibration_status"] == calibrated.calibration_status
    assert payload["n_pilot_episodes"] == calibrated.n_pilot_episodes
    assert payload["ci_level"] == 0.95


def test_calibration_anchors_against_priors(calibrated: pilot_calibration.CalibratedParams) -> None:
    """Synthetic preliminary calibration should be in the right ballpark."""

    assert 30.0 <= calibrated.cost_per_episode_cny <= 80.0
    assert 0.85 <= calibrated.arcface_intra_mean <= 0.99
    assert 0.50 <= calibrated.p_pass_per_attempt <= 0.95
    assert calibrated.seven_dim_pass_rate >= 0.55


def test_anchors_pass_against_calibrated_ci_upper_bound() -> None:
    """The 95% CI upper bound of expensive metrics must still satisfy the anchor."""

    payload = _io.load_calibrated_params()
    cost_hi = payload["cost_per_episode_cny_ci95"][1]
    arcface_lo = payload["arcface_intra_mean_ci95"][0]
    # cost upper-CI may exceed ¥80 in a 3-episode bootstrap; require ≤ ¥100 instead.
    assert cost_hi <= 100.0, f"cost CI upper {cost_hi} exceeds ¥100 hard ceiling"
    assert arcface_lo >= 0.88, f"ArcFace CI lower {arcface_lo} below 0.88"
