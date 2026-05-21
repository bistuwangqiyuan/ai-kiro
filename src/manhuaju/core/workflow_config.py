"""Workflow + distribution config loader (system.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowConfig:
    mode: str = "autopilot"  # autopilot | supervised
    candidates_per_shot: int = 1
    stages: tuple[str, ...] = (
        "analyze",
        "assets",
        "prompts",
        "draw",
        "rough_cut",
        "fine_cut",
    )


@dataclass(frozen=True)
class DistributionConfig:
    default_platform: str = "douyin"
    watermark: bool = False


def load_workflow_config(raw: dict[str, Any] | None) -> WorkflowConfig:
    wf = (raw or {}).get("workflow") or {}
    stages = wf.get("stages") or list(WorkflowConfig().stages)
    return WorkflowConfig(
        mode=str(wf.get("mode", "autopilot")),
        candidates_per_shot=int(wf.get("candidates_per_shot", 3)),
        stages=tuple(str(s) for s in stages),
    )


def load_distribution_config(raw: dict[str, Any] | None) -> DistributionConfig:
    dist = (raw or {}).get("distribution") or {}
    return DistributionConfig(
        default_platform=str(dist.get("default_platform", "douyin")),
        watermark=bool(dist.get("watermark", False)),
    )
