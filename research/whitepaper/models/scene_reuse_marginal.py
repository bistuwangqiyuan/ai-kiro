"""Scene-library reuse marginal-savings curve.

Cumulative reuse rate after N scenes is approximated as
``r(N) = 1 - exp(-k·N)``. Calibration of ``k`` comes from coverage data of
genre/atmosphere combinations; defaults give r(50)≈0.73, r(200)≈0.95.

Cost saving per episode:
    saving_cny = (1 - r(N)) → 0   ⇒   cost(scene_gen) → 0 incrementally.
"""

from __future__ import annotations

import numpy as np

from . import _io


def reuse_rate(library_size: int, k: float = 0.026) -> float:
    return float(1.0 - np.exp(-k * library_size))


def cost_per_episode_with_reuse(
    library_size: int,
    n_scenes_per_episode: int = 6,
    scene_unit_price_cny: float | None = None,
    k: float = 0.026,
) -> dict[str, float]:
    if scene_unit_price_cny is None:
        scene_unit_price_cny = float(
            _io.load_pricing("volcengine_manhuaju_2026").payload["endpoints"]["scene_generate"]["price"]
        )
    r = reuse_rate(library_size, k=k)
    fresh = n_scenes_per_episode * (1 - r)
    saved_cny = n_scenes_per_episode * scene_unit_price_cny * r
    return {
        "library_size": library_size,
        "reuse_rate": round(r, 4),
        "fresh_scenes_needed": round(fresh, 3),
        "scene_cost_per_ep_cny": round(fresh * scene_unit_price_cny, 3),
        "saving_per_ep_cny": round(saved_cny, 3),
    }


def summary() -> dict[str, object]:
    out: dict[str, object] = {"curve": []}
    for size in (10, 25, 50, 100, 200, 500, 1000):
        out["curve"].append(cost_per_episode_with_reuse(size))  # type: ignore[union-attr]
    out["k_default"] = 0.026
    out["asymptotic_reuse_rate"] = 1.0
    out["library_size_for_90pct"] = int(np.ceil(np.log(10) / 0.026))
    return out
