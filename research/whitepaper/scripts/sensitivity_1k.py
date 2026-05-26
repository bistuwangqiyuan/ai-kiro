"""1000-trial sensitivity analysis for the headline numbers.

Vary the four most uncertain inputs (retry_factor, scene_reuse_rate,
target_seconds, n_characters) within plausible ranges and see how the
Tier-M per-episode cost shifts. Output: `data/computed/sensitivity_1k.json`.
"""

from __future__ import annotations

import argparse
import os

import numpy as np

from research.whitepaper import SEED
from research.whitepaper.models import _io, cost_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=int(os.environ.get("MANHUAJU_WP_SEED", SEED)))
    parser.add_argument("--n", type=int, default=1000)
    args = parser.parse_args(argv)
    rng = np.random.default_rng(args.seed)

    samples = []
    for _ in range(args.n):
        retry = float(np.clip(rng.normal(0.18, 0.06), 0.05, 0.45))
        reuse = float(np.clip(rng.normal(0.40, 0.15), 0.0, 0.85))
        secs = int(np.clip(rng.normal(75, 15), 60, 120))
        chars = int(np.clip(rng.normal(4, 1.2), 2, 8))
        ec = cost_model.per_episode_cost(
            tier="M",
            target_seconds=secs,
            n_characters=chars,
            retry_factor=retry,
            scene_reuse_rate=reuse,
        )
        samples.append(ec.total_with_retry_cny)

    arr = np.asarray(samples)
    out = {
        "n_trials": int(args.n),
        "mean_cny": float(arr.mean()),
        "p50_cny": float(np.quantile(arr, 0.50)),
        "p95_cny": float(np.quantile(arr, 0.95)),
        "p99_cny": float(np.quantile(arr, 0.99)),
        "exceeds_80_rate": float((arr > 80).mean()),
        "exceeds_100_rate": float((arr > 100).mean()),
    }
    p = _io.write_computed("sensitivity_1k", out)
    print(f"[sensitivity] {args.n} trials → mean={out['mean_cny']:.2f} p95={out['p95_cny']:.2f} (exceed80 rate={out['exceeds_80_rate']:.3f})")
    print(f"[sensitivity] written: {p}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
