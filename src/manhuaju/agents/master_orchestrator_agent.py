"""MasterOrchestratorAgent — top-level driver (REQ-MO-001..010).

This agent doesn't run the pipeline itself in the M2 mock; it just records
project-level transitions and lifecycle events. The real pipeline is driven
by `manhuaju.pipelines.project_flow`.
"""

from __future__ import annotations

from manhuaju.core.agent_base import AgentRunRequest, AgentRunResponse, BaseAgent


class MasterOrchestratorAgent(BaseAgent):
    name = "MasterOrchestratorAgent"

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        action = req.inputs.get("action", "noop")
        self.ctx.bus.publish(
            f"manhuaju.event.master.{action}",
            project_id=req.context.project_id,
            payload=req.inputs.get("payload", {}),
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"action": action},
            metrics={},
        )
