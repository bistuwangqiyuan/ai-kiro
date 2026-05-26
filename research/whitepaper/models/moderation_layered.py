"""Dual-layer moderation false-negative analysis (Beta-binomial).

Layer 1: ByteDance content audit (text + image).
Layer 2: LLM judge (chosen from doubao_pro / deepseek_v4 / qwen_max).

If both layers must flag (AND gate, conservative-block) the FNR multiplies:
    FNR_AND = FNR_1 * FNR_2.

We use a Beta(α, β) posterior with α = (1 - fnr) * n_calibration,
β = fnr * n_calibration to derive 95% CI on the AND-gate FNR.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import _io


@dataclass(frozen=True)
class ModerationResult:
    layer1: str
    layer2: str
    point_fnr_layer1: float
    point_fnr_layer2: float
    point_fnr_and: float
    ci95_lower: float
    ci95_upper: float
    cost_per_call_cny: float

    def as_dict(self) -> dict[str, float | str]:
        return {
            "layer1": self.layer1,
            "layer2": self.layer2,
            "fnr_layer1": round(self.point_fnr_layer1, 6),
            "fnr_layer2": round(self.point_fnr_layer2, 6),
            "fnr_and_point": round(self.point_fnr_and, 8),
            "fnr_and_ci95_lower": round(self.ci95_lower, 8),
            "fnr_and_ci95_upper": round(self.ci95_upper, 8),
            "cost_per_call_cny": round(self.cost_per_call_cny, 4),
        }


def _bb_ci(rng: np.random.Generator, fnr: float, n_calibration: int = 5000, n_samples: int = 50_000) -> tuple[float, float]:
    """Bootstrap 95% CI under Beta(α, β) posterior with vague Beta(1,1) prior."""

    a = max(fnr * n_calibration + 1, 1.0)
    b = max((1 - fnr) * n_calibration + 1, 1.0)
    samples = rng.beta(a, b, n_samples)
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def evaluate(rng: np.random.Generator, layer2_provider: str = "doubao_pro") -> ModerationResult:
    df = _io.load_bench("moderation_fpr_fnr").payload
    l1 = df[df["provider"] == "bytedance_image_audit"].iloc[0]
    l2_lookup = {
        "doubao_pro": "llm_judge_doubao_pro",
        "deepseek_v4": "llm_judge_deepseek_v4",
        "qwen_max": "llm_judge_qwen_max",
    }[layer2_provider]
    l2 = df[df["provider"] == l2_lookup].iloc[0]

    fnr1 = float(l1["false_negative_rate"])
    fnr2 = float(l2["false_negative_rate"])
    fnr_and = fnr1 * fnr2

    lo1, hi1 = _bb_ci(rng, fnr1)
    lo2, hi2 = _bb_ci(rng, fnr2)
    # Independent layers ⇒ CI of product via simulation
    a1 = fnr1 * 5000 + 1
    b1 = (1 - fnr1) * 5000 + 1
    a2 = fnr2 * 5000 + 1
    b2 = (1 - fnr2) * 5000 + 1
    s1 = rng.beta(a1, b1, 50_000)
    s2 = rng.beta(a2, b2, 50_000)
    prod = s1 * s2
    lo = float(np.quantile(prod, 0.025))
    hi = float(np.quantile(prod, 0.975))

    cost = float(l1["price_per_call_cny"]) + float(l2["price_per_call_cny"])

    return ModerationResult(
        layer1=str(l1["provider"]),
        layer2=str(l2["provider"]),
        point_fnr_layer1=fnr1,
        point_fnr_layer2=fnr2,
        point_fnr_and=fnr_and,
        ci95_lower=lo,
        ci95_upper=hi,
        cost_per_call_cny=cost,
    )


def summary(rng: np.random.Generator) -> dict[str, object]:
    out: dict[str, object] = {}
    for prov in ("doubao_pro", "deepseek_v4", "qwen_max"):
        out[prov] = evaluate(rng, layer2_provider=prov).as_dict()
    out["target_max_fnr_and_ci_upper"] = 0.001
    return out
