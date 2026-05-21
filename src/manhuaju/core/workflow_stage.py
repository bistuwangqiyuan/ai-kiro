"""Six-step commercial workflow stages (REQ-WF-001)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from manhuaju.core.event_bus import InMemoryEventBus


class WorkflowStage(StrEnum):
    ANALYZE = "analyze"
    ASSETS = "assets"
    PROMPTS = "prompts"
    DRAW = "draw"
    ROUGH_CUT = "rough_cut"
    FINE_CUT = "fine_cut"
    DISTRIBUTION = "distribution"


STAGE_ORDER: tuple[WorkflowStage, ...] = (
    WorkflowStage.ANALYZE,
    WorkflowStage.ASSETS,
    WorkflowStage.PROMPTS,
    WorkflowStage.DRAW,
    WorkflowStage.ROUGH_CUT,
    WorkflowStage.FINE_CUT,
    WorkflowStage.DISTRIBUTION,
)


def emit_workflow_stage(
    bus: InMemoryEventBus,
    *,
    project_id: str,
    stage: WorkflowStage,
    episode_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    bus.publish(
        "manhuaju.event.workflow.stage",
        project_id=project_id,
        episode_id=episode_id,
        payload={"stage": stage.value, **(payload or {})},
    )
