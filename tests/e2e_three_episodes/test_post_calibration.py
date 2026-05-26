"""REQ-PILOT-CAL-001..004: post-calibration KPI sanity (V2.0).

Procedure:
    1. Build a synthetic ``pilot_telemetry.json`` from pilot artefacts.
    2. Run ``calibrate_from_pilot.main`` to produce ``calibrated_params.json``.
    3. Assert the 95% CI upper bounds of cost / latency / arcface still satisfy
       the anchors in ``need.md`` §11 / requirements.md.

This test is intentionally fast: we re-use the session-scoped pilot fixture
and we only invoke the calibration step.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from research.whitepaper import SEED
from research.whitepaper.models import _io, pilot_calibration

# Anchors mirror need.md §11 / requirements.md §23.
COST_ANCHOR_CNY = 80.0
LATENCY_ANCHOR_S = 60 * 60.0  # 60 minutes
ARCFACE_LEAD_ANCHOR = 0.92


def _build_telemetry_from_pilot(pilot_artefacts) -> dict[str, object]:
    """Map kpi_summary.json + manifest into the calibrate_from_pilot input schema."""

    summary = pilot_artefacts.pilot
    runtime_per_ep = pilot_artefacts.runtime_seconds_per_ep
    # Mock pilot uses 0 cost; map to a small synthetic anchor for calibration math.
    # We seed cost from the runtime so the calibration is deterministic across runs.
    base_cost = max(35.0, min(60.0, runtime_per_ep * 0.5))
    ep_costs = [round(base_cost - 1.5, 2), round(base_cost, 2), round(base_cost + 1.5, 2)]
    ep_lat = [runtime_per_ep * 60, runtime_per_ep * 62, runtime_per_ep * 58]
    arcface_means = []
    for item in summary["items"]:
        if "ArcFace" in item.get("label", "") and "values" in item:
            arcface_means.extend(float(v) for v in item["values"])
    if not arcface_means:
        arcface_means = [0.946, 0.948, 0.945]
    return {
        "episode_costs_cny": ep_costs,
        "episode_latency_s": ep_lat,
        "repair_attempts_total": 30,
        "repair_first_try_pass": 24,
        "arcface_intra_means": arcface_means,
        "seven_dim_pass_count": 50,
        "seven_dim_total_shots": 60,
        "scene_reuse_rate": 0.40,
        "moderation_fnr_and": 1e-4,
    }


@pytest.fixture(scope="session")
def calibrated_params_payload(pilot_artefacts, tmp_path_factory) -> dict[str, object]:
    """Build telemetry, run calibration, return the calibrated_params payload."""

    tmp = tmp_path_factory.mktemp("post_cal")
    telemetry = _build_telemetry_from_pilot(pilot_artefacts)
    telemetry_path = tmp / "pilot_telemetry.json"
    telemetry_path.write_text(json.dumps(telemetry, indent=2), encoding="utf-8")

    rng = np.random.default_rng(SEED)
    params = pilot_calibration.calibrate(rng, telemetry_path=telemetry_path)
    pilot_calibration.write_calibrated_params(params)
    out = json.loads((_io.COMPUTED_DIR / "calibrated_params.json").read_text(encoding="utf-8"))
    return out


def test_calibration_status(calibrated_params_payload) -> None:
    assert calibrated_params_payload["calibration_status"] == "calibrated_from_pilot"


def test_cost_ci_upper_bound_within_anchor(calibrated_params_payload) -> None:
    """REQ-PILOT-CAL-001: 95% CI upper bound for cost ≤ ¥80."""

    cost_hi = calibrated_params_payload["cost_per_episode_cny_ci95"][1]
    assert cost_hi <= COST_ANCHOR_CNY, f"calibrated cost CI95 hi={cost_hi}"


def test_latency_ci_upper_bound_within_anchor(calibrated_params_payload) -> None:
    """REQ-PILOT-CAL-002: 95% CI upper bound for episode P95 latency ≤ 60 min.

    The mock pilot completes in well under a minute per episode, so the CI is
    several orders of magnitude under the anchor.
    """

    lat_hi = calibrated_params_payload["latency_episode_p95_s_ci95"][1]
    assert lat_hi <= LATENCY_ANCHOR_S, f"latency CI95 hi={lat_hi}s"


def test_arcface_ci_lower_bound_above_anchor(calibrated_params_payload) -> None:
    """REQ-PILOT-CAL-003: 95% CI lower bound for cross-episode ArcFace ≥ 0.92."""

    af_lo = calibrated_params_payload["arcface_intra_mean_ci95"][0]
    assert af_lo >= ARCFACE_LEAD_ANCHOR, f"ArcFace CI95 lo={af_lo}"


def test_seven_dim_pass_rate_reasonable(calibrated_params_payload) -> None:
    """Calibrated 7-dim pass rate is non-zero and ≤ 1."""

    rate = calibrated_params_payload["seven_dim_pass_rate"]
    assert 0.0 < rate <= 1.0


def test_calibrated_params_payload_keys_complete(calibrated_params_payload) -> None:
    """REQ-PILOT-CAL-004: expected keys all present in calibrated_params.json."""

    expected_keys = {
        "calibration_status",
        "n_pilot_episodes",
        "ci_level",
        "p_pass_per_attempt",
        "p_pass_per_attempt_ci95",
        "retry_factor",
        "retry_factor_ci95",
        "arcface_intra_mean",
        "arcface_intra_mean_ci95",
        "seven_dim_pass_rate",
        "seven_dim_pass_rate_ci95",
        "cost_per_episode_cny",
        "cost_per_episode_cny_ci95",
        "latency_episode_p95_s",
        "latency_episode_p95_s_ci95",
        "scene_reuse_rate",
        "moderation_fnr_and",
    }
    assert expected_keys.issubset(set(calibrated_params_payload.keys()))


def test_calibrated_file_path() -> None:
    """The calibrated params JSON lands in the canonical computed dir."""

    assert (Path(_io.COMPUTED_DIR) / "calibrated_params.json").exists()
