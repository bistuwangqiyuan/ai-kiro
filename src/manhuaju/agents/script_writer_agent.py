"""ScriptWriterAgent — episode -> Script (REQ-SW-001..010)."""

from __future__ import annotations

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.utils.canonical_json import sha256_of, to_canonical


class ScriptWriterAgent(BaseAgent):
    name = "ScriptWriterAgent"

    def __init__(self, ctx: AgentContext, *, llm: MockLLMAdapter) -> None:
        super().__init__(ctx)
        self.llm = llm

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        ep = req.inputs["episode"]
        chars = req.inputs["characters"]
        seed = req.seed or 1
        script = self.llm.write_script(episode=ep, characters=chars, seed=seed)
        body = to_canonical(script)
        path = self.ctx.storage.write_text(
            f"{req.context.project_id}/06_scripts/{ep['episode_id']}.json", body
        )
        sha = sha256_of(script)
        self.ctx.provenance.record(
            artefact_uri=str(path),
            sha256=sha,
            size=len(body.encode("utf-8")),
            producer_agent=self.name,
            seed=seed,
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"script": script},
            metrics={
                "scenes": float(len(script["scenes"])),
                "shots": float(sum(len(s["shots"]) for s in script["scenes"])),
            },
        )
