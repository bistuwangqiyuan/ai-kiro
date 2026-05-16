"""StoryboardDirectorAgent — Script -> Storyboard (REQ-SD-001..010)."""

from __future__ import annotations

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.utils.canonical_json import sha256_of, to_canonical


class StoryboardDirectorAgent(BaseAgent):
    name = "StoryboardDirectorAgent"

    def __init__(self, ctx: AgentContext, *, llm: MockLLMAdapter) -> None:
        super().__init__(ctx)
        self.llm = llm

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        script = req.inputs["script"]
        style_sha = req.inputs["style_sha"]
        seed = req.seed or 1
        sb = self.llm.storyboard(script=script, style_sha=style_sha, seed=seed)
        body = to_canonical(sb)
        path = self.ctx.storage.write_text(
            f"{req.context.project_id}/07_storyboards/{sb['episode_id']}.json", body
        )
        sha = sha256_of(sb)
        self.ctx.provenance.record(
            artefact_uri=str(path),
            sha256=sha,
            size=len(body.encode("utf-8")),
            producer_agent=self.name,
            seed=seed,
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"storyboard": sb},
            metrics={"shots": float(len(sb["shots"]))},
        )
