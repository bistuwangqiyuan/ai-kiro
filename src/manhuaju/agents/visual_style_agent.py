"""VisualStyleAgent — StyleLock (REQ-VS-001..005)."""

from __future__ import annotations

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.utils.canonical_json import sha256_of, to_canonical


class VisualStyleAgent(BaseAgent):
    name = "VisualStyleAgent"

    def __init__(self, ctx: AgentContext, *, llm: MockLLMAdapter) -> None:
        super().__init__(ctx)
        self.llm = llm

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        bp = req.inputs["blueprint"]
        cfg = req.inputs["config"]
        style = self.llm.style_lock(project_id=req.context.project_id, blueprint=bp, config=cfg)
        body = to_canonical(style)
        path = self.ctx.storage.write_text(
            f"{req.context.project_id}/05_style/style_lock.json", body
        )
        sha = sha256_of(style)
        self.ctx.provenance.record(
            artefact_uri=str(path),
            sha256=sha,
            size=len(body.encode("utf-8")),
            producer_agent=self.name,
            seed=req.seed or 0,
        )
        self.ctx.bus.publish(
            "manhuaju.event.style.locked",
            project_id=req.context.project_id,
            payload={"style_sha": sha},
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"style_lock": style},
            metrics={"style_sha_len": float(len(sha))},
        )
