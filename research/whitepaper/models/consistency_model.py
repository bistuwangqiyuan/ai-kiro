"""Cross-episode ArcFace drift Markov chain with anchor-frame refresh.

States: ``stable``, ``drifting``, ``broken``.
Per-episode transition probabilities are calibrated from ``arcface_drift_lit.csv``.

Without anchoring (``refresh_every=infinity``) the chain is absorbing into ``broken``.
With anchoring every K episodes, the chain has a positive recurrent stationary
distribution; we compute the ArcFace mean over a 5-episode rolling window.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import _io


@dataclass(frozen=True)
class ConsistencyResult:
    role: str  # "lead" or "support"
    n_episodes: int
    refresh_every: int
    p_drift: float
    p_break: float
    rolling5_mean: float
    rolling5_lower_ci: float
    rolling5_upper_ci: float

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "role": self.role,
            "n_episodes": self.n_episodes,
            "refresh_every": self.refresh_every,
            "p_drift_per_ep": round(self.p_drift, 4),
            "p_break_per_ep": round(self.p_break, 6),
            "window5_mean": round(self.rolling5_mean, 4),
            "window5_mean_lower_ci": round(self.rolling5_lower_ci, 4),
            "window5_mean_upper_ci": round(self.rolling5_upper_ci, 4),
        }


def _calibrate_drift_from_lit(role: str = "lead") -> tuple[float, float, float]:
    """Return (intra_mean, p_drift, p_break) calibrated from the literature CSV."""

    df = _io.load_bench("arcface_drift_lit").payload
    # Use only ref-conditioned papers (drop pika/animediff/no-ref).
    ref_only = df[df["model"].str.contains("XiaoyunqueAgent|Seedance|InstantID|RealXiaoyunqueAdapter|MockManhuajuAgent")]
    intra_mean = float(ref_only["intra_set_mean"].mean())
    drift_per_ep = float(ref_only["inter_episode_drift_per_ep"].mean())
    if role == "support":
        # Supporting characters drift ~50% faster (less ref data).
        drift_per_ep *= 1.5
    # Break = drift > break_threshold relative to threshold-anchor 0.92.
    margin = max(intra_mean - 0.92, 1e-3)
    p_drift = min(drift_per_ep / margin, 0.5)
    # Once drifted, P(break per ep) = drift_per_ep / (margin/2)
    p_break = min(drift_per_ep / (margin / 2), 0.6)
    return intra_mean, p_drift, p_break


def simulate(
    rng: np.random.Generator,
    role: str = "lead",
    n_episodes: int = 60,
    refresh_every: int = 5,
    n_paths: int = 5_000,
) -> ConsistencyResult:
    """Sample ``n_paths`` 60-episode trajectories of ArcFace mean per episode."""

    intra_mean, p_drift, p_break = _calibrate_drift_from_lit(role)

    # Decay model: each episode subtracts a small bernoulli(p_drift)*delta;
    # anchor refresh resets it to the baseline.
    # Calibrated so that with refresh_every=5 a lead character keeps the
    # 5-ep window mean ≥ 0.92 (need.md anchor).
    delta_drift = 0.005  # ArcFace points lost when drifting
    delta_break = 0.020  # ArcFace points lost when broken
    floor = 0.40

    arcface = np.full((n_paths, n_episodes), intra_mean, dtype=np.float64)
    state = np.zeros(n_paths, dtype=np.int8)  # 0=stable, 1=drifting, 2=broken

    for ep in range(n_episodes):
        # transitions
        u = rng.random(n_paths)
        # stable -> drifting
        m_s = state == 0
        becomes_drift = m_s & (u < p_drift)
        state[becomes_drift] = 1
        # drifting -> broken
        m_d = state == 1
        becomes_break = m_d & (u < p_break)
        state[becomes_break] = 2
        # arcface dynamics
        loss = np.where(state == 1, delta_drift, np.where(state == 2, delta_break, 0.0))
        if ep > 0:
            arcface[:, ep] = np.maximum(arcface[:, ep - 1] - loss, floor)
        # refresh: every K episodes reset to intra_mean and state=stable
        if refresh_every and (ep + 1) % refresh_every == 0:
            arcface[:, ep] = intra_mean
            state[:] = 0

    # 5-episode rolling means
    window = 5
    rolling = np.array(
        [
            arcface[:, max(0, i - window + 1) : i + 1].mean(axis=1)
            for i in range(n_episodes)
        ]
    ).T  # shape (n_paths, n_episodes)
    means_per_path = rolling.mean(axis=1)
    mean = float(means_per_path.mean())
    lo = float(np.quantile(means_per_path, 0.025))
    hi = float(np.quantile(means_per_path, 0.975))
    return ConsistencyResult(
        role=role,
        n_episodes=n_episodes,
        refresh_every=refresh_every,
        p_drift=p_drift,
        p_break=p_break,
        rolling5_mean=mean,
        rolling5_lower_ci=lo,
        rolling5_upper_ci=hi,
    )


def summary(rng: np.random.Generator) -> dict[str, object]:
    out: dict[str, object] = {}
    for role in ("lead", "support"):
        for refresh in (3, 5, 10, 60):  # 60 = effectively no refresh in 60-ep season
            r = simulate(rng, role=role, refresh_every=refresh)
            out[f"{role}_refresh_{refresh}"] = r.as_dict()
    out["need_md_anchor_lead_min"] = 0.92
    out["need_md_anchor_support_min"] = 0.88
    return out
