"""StoryArchitectAgent — novel -> StoryBlueprint (REQ-SA-001..010)."""

from __future__ import annotations

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.adapters.moderation.mock_moderation_adapter import MockModerationAdapter
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.utils.canonical_json import sha256_of, to_canonical


class StoryArchitectAgent(BaseAgent):
    name = "StoryArchitectAgent"

    def __init__(self, ctx: AgentContext, *, llm: MockLLMAdapter, moderation: MockModerationAdapter) -> None:
        super().__init__(ctx)
        self.llm = llm
        self.moderation = moderation

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        novel_text: str = req.inputs["novel_text"]
        project_id: str = req.context.project_id
        seed: int = req.seed or 1
        # Moderation gate on input (REQ-IN-008 / F-020)
        mod = self.moderation.screen({"novel_text_head": novel_text[:512]})
        if mod["openai_hit"] or mod["bytedance_hit"]:
            return AgentRunResponse(
                status="failed",
                outputs={"reason": "redline_hit", "hits": mod["hits"]},
                metrics={"redline_hit": 1.0},
            )
        bp = self.llm.story_blueprint(novel_text=novel_text, project_id=project_id, seed=seed)
        # Persist as canonical JSON
        body = to_canonical(bp)
        key = f"{project_id}/01_blueprint/blueprint.json"
        path = self.ctx.storage.write_text(key, body)
        sha = sha256_of(bp)
        self.ctx.provenance.record(
            artefact_uri=str(path),
            sha256=sha,
            size=len(body.encode("utf-8")),
            producer_agent=self.name,
            seed=seed,
        )
        self.ctx.bus.publish(
            "manhuaju.event.blueprint.ready",
            project_id=project_id,
            payload={"blueprint_sha": sha},
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"blueprint": bp, "uri": str(path)},
            metrics={
                "faithfulness": bp["judge_scores"]["faithfulness"],
                "coverage": bp["judge_scores"]["coverage"],
                "structure": bp["judge_scores"]["structure"],
            },
        )
