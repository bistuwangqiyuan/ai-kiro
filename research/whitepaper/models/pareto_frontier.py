"""Cost / latency / quality Pareto frontier.

We treat tier ∈ {H, M, L} × parallelism ∈ {4, 8, 16, 32} ×
repair_p ∈ {0.65, 0.75, 0.85} as the discrete decision space (36 points)
and compute three objectives:

    f1 = expected per-episode cost (CNY)               (minimise)
    f2 = expected per-episode latency (seconds)        (minimise)
    f3 = expected QA pass-rate at threshold 8.0        (maximise)

A point ``a`` Pareto-dominates ``b`` iff every objective is at least as good
and at least one strictly better. We enumerate the 36 points and return the
non-dominated subset.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import cost_model, repair_convergence, sla_model


@dataclass(frozen=True)
class ParetoPoint:
    tier: str
    parallelism: int
    p_pass: float
    cost_cny: float
    latency_s: float
    quality: float

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "tier": self.tier,
            "parallelism": self.parallelism,
            "p_pass": self.p_pass,
            "cost_cny": round(self.cost_cny, 2),
            "latency_s": round(self.latency_s, 1),
            "quality": round(self.quality, 4),
        }


def _quality_proxy(p_pass: float) -> float:
    """Quality proxy: 7-dim pass rate scaled by tier's prior gain."""

    # Higher tier → tighter Beta priors. We only have analytical p_pass here;
    # the SevenDim model already returns this numerically. We use the
    # repair-convergence pass rate as a stand-in proxy.
    return min(p_pass + 0.10, 0.99)


def enumerate_points(rng: np.random.Generator) -> list[ParetoPoint]:
    points: list[ParetoPoint] = []
    for tier in ("H", "M", "L"):
        for par in (4, 8, 16, 32):
            for p_pass in (0.65, 0.75, 0.85):
                rep = repair_convergence.evaluate(p_pass_per_attempt=p_pass)
                ec = cost_model.per_episode_cost(tier=tier, retry_factor=rep.retry_factor)
                lat = sla_model.episode_latency_distribution(
                    rng,
                    n_samples=10_000,
                    parallel_video_slots=par,
                    repair_iterations_p95=rep.expected_attempts,
                )["episode"]["p95_s"]  # type: ignore[index]
                points.append(
                    ParetoPoint(
                        tier=tier,
                        parallelism=par,
                        p_pass=p_pass,
                        cost_cny=ec.total_with_retry_cny,
                        latency_s=float(lat),
                        quality=_quality_proxy(p_pass),
                    )
                )
    return points


def non_dominated(points: list[ParetoPoint]) -> list[ParetoPoint]:
    out: list[ParetoPoint] = []
    for p in points:
        dominated = False
        for q in points:
            if q is p:
                continue
            if (
                q.cost_cny <= p.cost_cny
                and q.latency_s <= p.latency_s
                and q.quality >= p.quality
                and (
                    q.cost_cny < p.cost_cny
                    or q.latency_s < p.latency_s
                    or q.quality > p.quality
                )
            ):
                dominated = True
                break
        if not dominated:
            out.append(p)
    return out


def summary(rng: np.random.Generator) -> dict[str, object]:
    points = enumerate_points(rng)
    front = non_dominated(points)
    return {
        "n_candidates": len(points),
        "n_frontier": len(front),
        "frontier": [p.as_dict() for p in sorted(front, key=lambda x: (x.cost_cny, x.latency_s))],
        "all_candidates": [p.as_dict() for p in points],
    }
