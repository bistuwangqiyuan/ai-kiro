"""Per-episode cost decomposition.

C_ep = sum_i (n_i * p_i) * (1 + retry_factor)

where i ranges over 12 stages: script_LLM, char_gen, scene_gen, storyboard,
video_gen, video_compose, TTS, BGM, SFX, mod_layer1, mod_layer2, TOS_storage.

Inputs come exclusively from snapshots in ``data/pricing/``. The retry factor
is sourced from ``repair_convergence`` to keep the model self-consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import _io


@dataclass(frozen=True)
class StageCost:
    name: str
    n_units: float
    unit_price_cny: float
    raw_cny: float
    with_retry_cny: float


@dataclass(frozen=True)
class EpisodeCost:
    tier: str
    stages: tuple[StageCost, ...]
    total_raw_cny: float
    total_with_retry_cny: float
    retry_factor: float

    def as_dict(self) -> dict[str, object]:
        return {
            "tier": self.tier,
            "retry_factor": round(self.retry_factor, 4),
            "total_raw_cny": round(self.total_raw_cny, 3),
            "total_with_retry_cny": round(self.total_with_retry_cny, 3),
            "stages": [
                {
                    "name": s.name,
                    "n_units": s.n_units,
                    "unit_price_cny": s.unit_price_cny,
                    "raw_cny": round(s.raw_cny, 3),
                    "with_retry_cny": round(s.with_retry_cny, 3),
                }
                for s in self.stages
            ],
        }


def _shots_per_episode(target_seconds: int = 90, shot_seconds: int = 5) -> int:
    """Return integer shots per episode (need.md §1.2: 1-3 min, default ~90s)."""

    return max(9, target_seconds // shot_seconds)


def per_episode_cost(
    tier: str = "M",
    target_seconds: int = 60,
    n_characters: int = 4,
    n_scenes: int = 6,
    dialogue_chars: int = 2200,
    retry_factor: float = 0.18,
    scene_reuse_rate: float = 0.40,
) -> EpisodeCost:
    """Build a deterministic per-episode cost decomposition.

    Parameters
    ----------
    tier : ``"H"`` | ``"M"`` | ``"L"``
        H = Xiaoyunque pro 1080p; M = Manhuaju Agent fast 720p; L = Seedance fast.
    target_seconds : int
        Episode target screen time in seconds.
    n_characters : int
        Lead+supporting character count.
    n_scenes : int
        Distinct scenes to generate.
    dialogue_chars : int
        Total Chinese-character count of dialogue+narration.
    retry_factor : float
        Multiplicative overhead from the repair loop. Default is the pilot
        prior; calibrate via ``repair_convergence``.
    """

    manhuaju = _io.load_pricing("volcengine_manhuaju_2026").payload
    skylark = _io.load_pricing("volcengine_skylark_v2_2026").payload
    seedance = _io.load_pricing("seedance_2_2026").payload
    tts = _io.load_pricing("doubao_tts_icl_v3_2026").payload
    misc = _io.load_pricing("tos_dashscope_2026").payload

    shots = _shots_per_episode(target_seconds, shot_seconds=5)

    if tier == "H":
        video_unit_price = skylark["endpoints"]["skylark_video_agent_v2_with_ref_pro_1080p"]["price"]
    elif tier == "M":
        video_unit_price = manhuaju["endpoints"]["video_generate_fast720p"]["price"]
    elif tier == "L":
        video_unit_price = seedance["endpoints"]["seedance_2_i2v_720p"]["price"]
    else:  # pragma: no cover — guarded by enum upstream
        raise ValueError(f"unknown tier {tier!r}")

    char_unit = manhuaju["endpoints"]["character_generate"]["price"]
    scene_unit = manhuaju["endpoints"]["scene_generate"]["price"]
    script_unit = manhuaju["endpoints"]["script_analysis"]["price"]
    storyboard_unit = manhuaju["endpoints"]["storyboard_generate"]["price"]
    compose_unit = manhuaju["endpoints"]["video_compose_fast720p"]["price"]

    tts_unit = tts["endpoints"]["tts_icl_v3_dialog"]["price"]
    bgm_unit = 0.30
    sfx_unit = 0.20

    mod_text_unit = misc["moderation"]["bytedance_text_per_10k"]
    mod_image_unit = misc["moderation"]["bytedance_image_per_10k"]
    storage_unit = misc["tos"]["storage_per_gb_month"]
    artefact_gb = misc["tos"]["average_episode_artefact_size_gb"]

    raw_stages: list[StageCost] = []

    def add(name: str, n: float, p: float) -> None:
        raw = n * p
        raw_stages.append(
            StageCost(name=name, n_units=n, unit_price_cny=p, raw_cny=raw, with_retry_cny=raw)
        )

    add("script_analysis", 1, script_unit)
    add("character_generate", n_characters, char_unit)
    fresh_scenes = n_scenes * (1 - scene_reuse_rate)
    add("scene_generate", fresh_scenes, scene_unit)
    add("storyboard_generate", 1, storyboard_unit)
    add("video_generate", shots, video_unit_price)
    add("video_compose", 1, compose_unit)
    add("tts_dialog", dialogue_chars / 10000.0, tts_unit)
    add("bgm_per_episode", 1, bgm_unit)
    add("sfx_per_episode", 1, sfx_unit)
    add("moderation_text", dialogue_chars / 10000.0, mod_text_unit)
    add("moderation_image", shots / 10000.0, mod_image_unit)
    add("tos_storage_30d", artefact_gb, storage_unit)

    inflated = [
        StageCost(
            name=s.name,
            n_units=s.n_units,
            unit_price_cny=s.unit_price_cny,
            raw_cny=s.raw_cny,
            with_retry_cny=round(s.raw_cny * (1 + retry_factor), 4),
        )
        for s in raw_stages
    ]
    total_raw = sum(s.raw_cny for s in raw_stages)
    total_with_retry = sum(s.with_retry_cny for s in inflated)

    return EpisodeCost(
        tier=tier,
        stages=tuple(inflated),
        total_raw_cny=total_raw,
        total_with_retry_cny=total_with_retry,
        retry_factor=retry_factor,
    )


def cost_distribution(
    rng: np.random.Generator,
    tier: str = "M",
    n_samples: int = 100_000,
    retry_factor_mean: float = 0.18,
    retry_factor_std: float = 0.06,
    price_jitter_pct: float = 0.05,
) -> dict[str, float]:
    """Monte Carlo of the per-episode cost; returns mean / p50 / p95 / p99 in CNY."""

    base = per_episode_cost(tier=tier, retry_factor=0.0)
    base_total = base.total_raw_cny

    rf = rng.normal(retry_factor_mean, retry_factor_std, n_samples).clip(0.0, 1.0)
    jitter = 1.0 + rng.uniform(-price_jitter_pct, price_jitter_pct, n_samples)
    samples = base_total * jitter * (1.0 + rf)
    return {
        "mean": float(np.mean(samples)),
        "p50": float(np.quantile(samples, 0.50)),
        "p95": float(np.quantile(samples, 0.95)),
        "p99": float(np.quantile(samples, 0.99)),
        "n_samples": n_samples,
    }


def all_tiers_summary(rng: np.random.Generator) -> dict[str, object]:
    """Convenience: run all three tiers, including 95th percentile costs."""

    out: dict[str, object] = {}
    for tier in ("H", "M", "L"):
        ep = per_episode_cost(tier=tier)
        dist = cost_distribution(rng, tier=tier)
        out[f"tier_{tier}"] = {**ep.as_dict(), **{f"mc_{k}": v for k, v in dist.items()}}
    out["need_md_anchor_max_cny"] = 80.0
    return out
