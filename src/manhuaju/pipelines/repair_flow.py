"""Repair-flow stub.

In M2 the repair logic lives inside `EpisodePipeline.run()` (the inner while
loop). This module exists for symmetry with the spec (design §10.4 calls for
a dedicated repair_flow); higher milestones will lift the loop out.
"""

from __future__ import annotations

from typing import Any

from manhuaju.agents.iteration_manager_agent import IterationManagerAgent
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, TraceContext


def plan_repairs(
    ctx: AgentContext,
    project_id: str,
    episode_id: str,
    *,
    shot_reports: list[dict[str, Any]],
    drifted: list[str],
) -> list[dict[str, Any]]:
    it = IterationManagerAgent(ctx)
    resp = it.run(
        AgentRunRequest(
            inputs={"shot_reports": shot_reports, "drifted": drifted},
            context=TraceContext(project_id=project_id, episode_id=episode_id),
        )
    )
    return list(resp.outputs["plans"])
