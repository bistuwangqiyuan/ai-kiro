"""DialogueOptimizerAgent — polish dialogue lines after script draft (REQ-WF-002)."""

from __future__ import annotations

from typing import Any

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.core.agent_base import AgentRunRequest, AgentRunResponse, BaseAgent


class DialogueOptimizerAgent(BaseAgent):
    name = "DialogueOptimizerAgent"

    def __init__(self, ctx, *, llm: MockLLMAdapter) -> None:
        super().__init__(ctx)
        self.llm = llm

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        script: dict[str, Any] = req.inputs["script"]
        optimized = dict(script)
        lines = []
        for dlg in script.get("dialogues", []):
            text = str(dlg.get("text", "")).strip()
            if len(text) > 40:
                text = text[:38] + "…"
            lines.append({**dlg, "text": text, "optimized": True})
        optimized["dialogues"] = lines
        self.ctx.bus.publish(
            "manhuaju.event.dialogue.optimized",
            project_id=req.context.project_id,
            episode_id=req.context.episode_id,
            payload={"lines": len(lines)},
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"script": optimized},
            metrics={"dialogue_lines": float(len(lines))},
        )
