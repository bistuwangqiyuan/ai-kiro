"""Seven-dimension QA scorer (REQ-QA7-001..007).

Proxy heuristics for mock/live until GPU judges are wired.
"""

from __future__ import annotations

import hashlib
from typing import Any

SEVEN_DIM_MIN = 7.0

DIMENSIONS = (
    "structure",
    "style_consistency",
    "detail_completeness",
    "clarity",
    "color_harmony",
    "no_breakdown",
    "intent_match",
)


def _stable_score(seed: str, base: float, spread: float = 1.5) -> float:
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    return round(min(10.0, max(0.0, base + (h % 1000) / 1000.0 * spread)), 2)


def score_shot(
    *,
    shot: dict[str, Any],
    render: dict[str, Any],
    style_sha: str,
) -> dict[str, float]:
    shot_id = shot.get("shot_id", "unknown")
    clauses = len(shot.get("prompt_brief", {}).get("clauses", []))
    degraded = bool(render.get("degraded"))
    base = 8.2 if not degraded else 6.8
    structure = _stable_score(f"{shot_id}:struct", base)
    style = _stable_score(f"{style_sha}:{shot_id}:style", base - 0.2)
    detail = _stable_score(f"{shot_id}:detail", base - 0.1)
    clarity = _stable_score(f"{shot_id}:clarity", base)
    color = _stable_score(f"{shot_id}:color", base - 0.15)
    no_break = _stable_score(f"{shot_id}:nobreak", base + 0.1)
    intent = _stable_score(f"{shot_id}:intent:{clauses}", base - 0.05)
    if clauses < 10:
        intent = min(intent, 6.5)
    return {
        "structure": structure,
        "style_consistency": style,
        "detail_completeness": detail,
        "clarity": clarity,
        "color_harmony": color,
        "no_breakdown": no_break,
        "intent_match": intent,
    }


def score_episode(
    *,
    storyboard: dict[str, Any],
    renders: list[dict[str, Any]],
    style_sha: str,
) -> dict[str, Any]:
    render_by_shot = {r["shot_id"]: r for r in renders}
    per_shot: dict[str, dict[str, float]] = {}
    for shot in storyboard.get("shots", []):
        sid = shot["shot_id"]
        per_shot[sid] = score_shot(
            shot=shot,
            render=render_by_shot.get(sid, {}),
            style_sha=style_sha,
        )
    dim_means = {
        dim: round(
            sum(s[dim] for s in per_shot.values()) / max(len(per_shot), 1),
            2,
        )
        for dim in DIMENSIONS
    }
    pass_all = all(v >= SEVEN_DIM_MIN for v in dim_means.values())
    return {
        "dimensions": dim_means,
        "per_shot": per_shot,
        "pass_all": pass_all,
        "min_dimension": min(dim_means.values()) if dim_means else 0.0,
    }
