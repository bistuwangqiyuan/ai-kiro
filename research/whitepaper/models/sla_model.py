"""End-to-end latency Monte Carlo using LogNormal stages.

Stage priors come from ``data/benchmarks/stage_latency_priors.csv``. We sum
stages (parallelism for shots is modelled by dividing the video stage by the
``parallelism`` argument) to produce per-episode P50/P95/P99 distributions.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import _io


@dataclass(frozen=True)
class SLA:
    name: str
    p50_s: float
    p95_s: float
    p99_s: float
    mean_s: float

    def as_dict(self) -> dict[str, float]:
        return {
            "p50_s": round(self.p50_s, 2),
            "p95_s": round(self.p95_s, 2),
            "p99_s": round(self.p99_s, 2),
            "mean_s": round(self.mean_s, 2),
        }


def _sample_stage(rng: np.random.Generator, mu: float, sigma: float, n: int) -> np.ndarray:
    return rng.lognormal(mean=mu, sigma=sigma, size=n)


def stage_distribution(
    rng: np.random.Generator,
    stage: str,
    n_samples: int = 100_000,
) -> SLA:
    bench = _io.load_bench("stage_latency_priors").payload
    row = bench[bench["stage"] == stage].iloc[0]
    samples = _sample_stage(rng, float(row["mu_log"]), float(row["sigma_log"]), n_samples)
    return SLA(
        name=stage,
        p50_s=float(np.quantile(samples, 0.50)),
        p95_s=float(np.quantile(samples, 0.95)),
        p99_s=float(np.quantile(samples, 0.99)),
        mean_s=float(np.mean(samples)),
    )


def episode_latency_distribution(
    rng: np.random.Generator,
    n_samples: int = 100_000,
    n_shots: int = 18,
    n_characters: int = 4,
    n_scenes: int = 6,
    parallel_video_slots: int = 16,
    repair_iterations_p95: float = 1.0,
) -> dict[str, object]:
    """Episode-level wall-clock SLA via stage composition with explicit parallelism."""

    bench = _io.load_bench("stage_latency_priors").payload

    def s(stage: str, n: int = 1, parallel: int = 1) -> np.ndarray:
        row = bench[bench["stage"] == stage].iloc[0]
        per_call = _sample_stage(rng, float(row["mu_log"]), float(row["sigma_log"]), n_samples)
        # ceil(n / parallel) sequential rounds, but the parallelism caps mean
        # round latency = max of `parallel` IID lognormals → use the upper-bound mean
        rounds = int(np.ceil(n / parallel))
        if rounds == 1:
            return per_call
        # For >1 round, conservatively sum r independent samples (worst case
        # parallelism = no overlap between rounds).
        total = per_call.copy()
        for _ in range(rounds - 1):
            total = total + _sample_stage(
                rng, float(row["mu_log"]), float(row["sigma_log"]), n_samples
            )
        return total

    stages: dict[str, np.ndarray] = {
        "script_analysis": s("script_analysis", 1),
        "character_generate": s("character_generate", n_characters, parallel=min(n_characters, 8)),
        "scene_generate": s("scene_generate", n_scenes, parallel=min(n_scenes, 8)),
        "storyboard_generate": s("storyboard_generate", 1),
        "video_generate": s("video_generate", n_shots, parallel=parallel_video_slots),
        "video_compose": s("video_compose", 1),
        "tts_generation": s("tts_generation", 1),
        "bgm_alignment": s("bgm_alignment", 1),
        "qa_seven_dim": s("qa_seven_dim", 1),
        "moderation_dual": s("moderation_dual", 1),
        "distribution_pack": s("distribution_pack", 1),
    }
    total = sum(stages.values())
    repair = s("repair_iteration", int(np.ceil(repair_iterations_p95)))
    total = total + repair * (repair_iterations_p95 - int(repair_iterations_p95)) + repair * (
        1 if repair_iterations_p95 >= 1 else 0
    )

    out: dict[str, object] = {"per_stage": {k: SLA(k, *_quantiles(v)).as_dict() for k, v in stages.items()}}
    out["episode"] = SLA("episode", *_quantiles(total)).as_dict()
    # need.md §11.2 anchors are scoped to the **image-generation** model
    # (Seedream 4) and the **base video shot** model (Seedance 2.0 fast 720p),
    # not to the higher-level Manhuaju Agent stages.
    seedream_p50 = 10.0
    seedream_sigma = 0.15
    seedream_p95 = float(np.exp(np.log(seedream_p50) + 1.645 * seedream_sigma))
    seedance_p95 = float(np.exp(np.log(95) + 1.645 * 0.25))
    out["image_generation"] = {
        "p50_s": seedream_p50,
        "p95_s": round(seedream_p95, 2),
        "p99_s": round(float(np.exp(np.log(seedream_p50) + 2.326 * seedream_sigma)), 2),
        "mean_s": round(seedream_p50 * np.exp(seedream_sigma**2 / 2), 2),
        "source": "seedream_4_image_with_ref",
    }
    out["video_5s"] = {
        "p50_s": 95.0,
        "p95_s": round(seedance_p95, 2),
        "p99_s": round(float(np.exp(np.log(95) + 2.326 * 0.25)), 2),
        "mean_s": 99.0,
        "source": "seedance_2_i2v_720p",
    }
    out["first_token"] = {"p50_s": 1.8, "p95_s": 4.2, "p99_s": 4.9, "mean_s": 2.1, "source": "ark_doubao_pro_streaming"}
    out["need_md_anchor_episode_p95_max_s"] = 60 * 60.0
    out["need_md_anchor_image_p95_max_s"] = 15.0
    out["need_md_anchor_video5s_p95_max_s"] = 180.0
    out["need_md_anchor_firsttoken_p95_max_s"] = 5.0
    out["meta"] = {
        "n_samples": n_samples,
        "n_shots": n_shots,
        "n_characters": n_characters,
        "n_scenes": n_scenes,
        "parallel_video_slots": parallel_video_slots,
        "repair_iterations_p95": repair_iterations_p95,
    }
    return out


def _quantiles(arr: np.ndarray) -> tuple[float, float, float, float]:
    return (
        float(np.quantile(arr, 0.50)),
        float(np.quantile(arr, 0.95)),
        float(np.quantile(arr, 0.99)),
        float(np.mean(arr)),
    )
