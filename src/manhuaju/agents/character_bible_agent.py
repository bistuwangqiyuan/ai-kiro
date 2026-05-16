"""CharacterBibleAgent — per-character bible (REQ-CB-001..010)."""

from __future__ import annotations

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.utils.canonical_json import sha256_of, to_canonical


class CharacterBibleAgent(BaseAgent):
    name = "CharacterBibleAgent"

    def __init__(self, ctx: AgentContext, *, llm: MockLLMAdapter) -> None:
        super().__init__(ctx)
        self.llm = llm

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        characters = req.inputs["characters"]
        blueprint = req.inputs["blueprint"]
        seed = req.seed or 1
        bibles = []
        for stub in characters:
            bible = self.llm.character_bible(character_stub=stub, blueprint=blueprint, seed=seed)
            body = to_canonical(bible)
            key = f"{req.context.project_id}/03_bibles/{bible['char_id']}.json"
            path = self.ctx.storage.write_text(key, body)
            sha = sha256_of(bible)
            self.ctx.provenance.record(
                artefact_uri=str(path),
                sha256=sha,
                size=len(body.encode("utf-8")),
                producer_agent=self.name,
                seed=seed,
            )
            bibles.append(bible)
        self.ctx.bus.publish(
            "manhuaju.event.bibles.ready",
            project_id=req.context.project_id,
            payload={"count": len(bibles)},
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"bibles": bibles},
            metrics={"bibles": float(len(bibles))},
        )
