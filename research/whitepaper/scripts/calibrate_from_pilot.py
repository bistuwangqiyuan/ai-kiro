"""Read 3-episode mock-pipeline telemetry and (re-)write `calibrated_params.json`.

Usage:
    python -m research.whitepaper.scripts.calibrate_from_pilot \
        --telemetry tests/e2e_three_episodes/reports/pilot_telemetry.json
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

import numpy as np

from research.whitepaper import SEED
from research.whitepaper.models import _io, pilot_calibration


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry", type=Path, default=None,
                        help="Path to pilot telemetry JSON (defaults to data/computed/pilot_telemetry.json).")
    parser.add_argument("--seed", type=int,
                        default=int(os.environ.get("MANHUAJU_WP_SEED", SEED)))
    args = parser.parse_args(argv)

    rng = np.random.default_rng(args.seed)

    telemetry_path = args.telemetry
    if telemetry_path and telemetry_path.exists():
        # also copy to computed dir so re-runs of run_all see it
        shutil.copy(telemetry_path, _io.COMPUTED_DIR / "pilot_telemetry.json")
        params = pilot_calibration.calibrate(rng, telemetry_path=_io.COMPUTED_DIR / "pilot_telemetry.json")
    else:
        params = pilot_calibration.calibrate(rng)

    out_path = pilot_calibration.write_calibrated_params(params)
    print(f"[calibrate] status   : {params.calibration_status}")
    print(f"[calibrate] n_pilot  : {params.n_pilot_episodes}")
    print(f"[calibrate] cost     : ¥{params.cost_per_episode_cny:.2f} (CI95 {params.cost_per_episode_cny_ci95})")
    print(f"[calibrate] latency  : {params.latency_episode_p95_s:.1f}s (CI95 {params.latency_episode_p95_s_ci95})")
    print(f"[calibrate] arcface  : {params.arcface_intra_mean:.4f} (CI95 {params.arcface_intra_mean_ci95})")
    print(f"[calibrate] written  : {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
