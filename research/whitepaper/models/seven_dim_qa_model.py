"""7-dimension QA scoring under Beta-distributed dimensions.

Each of the 7 dimensions defined in ``need.md §6.1`` is modelled as a Beta(α, β)
random variable on [0, 10] (we draw Beta on [0,1] then multiply by 10).

A shot ``passes`` if every dimension ≥ ``threshold`` (default 8.0). The pass
rate is estimated by Monte Carlo with the priors in
``data/benchmarks/seven_dim_qa_priors.csv``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import _io


@dataclass(frozen=True)
class SevenDimResult:
    threshold: float
    n_samples: int
    pass_rate: float
    per_dim_pass_rate: dict[str, float]
    mean_score: float
    worst_dim: str
    mean_per_dim: dict[str, float]

    def as_dict(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "n_samples": self.n_samples,
            "pass_rate": round(self.pass_rate, 4),
            "per_dim_pass_rate": {k: round(v, 4) for k, v in self.per_dim_pass_rate.items()},
            "mean_score": round(self.mean_score, 3),
            "worst_dim": self.worst_dim,
            "mean_per_dim": {k: round(v, 3) for k, v in self.mean_per_dim.items()},
        }


def evaluate(rng: np.random.Generator, threshold: float = 8.0, n_samples: int = 200_000) -> SevenDimResult:
    df = _io.load_bench("seven_dim_qa_priors").payload
    dims = df["dimension"].tolist()
    scores = np.zeros((n_samples, len(dims)), dtype=np.float64)
    for i, _ in enumerate(dims):
        a = float(df.iloc[i]["prior_alpha"])
        b = float(df.iloc[i]["prior_beta"])
        scores[:, i] = rng.beta(a, b, n_samples) * 10.0
    pass_per_dim = (scores >= threshold).mean(axis=0)
    pass_all = (scores >= threshold).all(axis=1).mean()
    mean_per_dim = scores.mean(axis=0)
    worst_idx = int(np.argmin(mean_per_dim))
    return SevenDimResult(
        threshold=threshold,
        n_samples=n_samples,
        pass_rate=float(pass_all),
        per_dim_pass_rate={d: float(p) for d, p in zip(dims, pass_per_dim, strict=True)},
        mean_score=float(scores.mean()),
        worst_dim=dims[worst_idx],
        mean_per_dim={d: float(m) for d, m in zip(dims, mean_per_dim, strict=True)},
    )


def summary(rng: np.random.Generator) -> dict[str, object]:
    out: dict[str, object] = {}
    for thr in (7.0, 7.5, 8.0, 8.5, 9.0):
        out[f"threshold_{thr}"] = evaluate(rng, threshold=thr).as_dict()
    out["need_md_anchor_threshold"] = 8.0
    out["need_md_anchor_min_pass_rate"] = 0.85
    return out
