"""EpisodePlannerAgent — StoryBlueprint -> EpisodePlan (REQ-EP-001..010)."""

from __future__ import annotations

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.utils.canonical_json import sha256_of, to_canonical


class EpisodePlannerAgent(BaseAgent):
    name = "EpisodePlannerAgent"

    def __init__(self, ctx: AgentContext, *, llm: MockLLMAdapter) -> None:
        super().__init__(ctx)
        self.llm = llm

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        bp = req.inputs["blueprint"]
        episode_count: int = req.inputs.get("episode_count", 3)
        seed: int = req.seed or 1
        plan = self.llm.episode_plan(blueprint=bp, episode_count=episode_count, seed=seed)
        body = to_canonical(plan)
        key = f"{req.context.project_id}/02_plan/episode_plan.json"
        path = self.ctx.storage.write_text(key, body)
        sha = sha256_of(plan)
        self.ctx.provenance.record(
            artefact_uri=str(path),
            sha256=sha,
            size=len(body.encode("utf-8")),
            producer_agent=self.name,
            seed=seed,
        )
        self.ctx.bus.publish(
            "manhuaju.event.plan.ready",
            project_id=req.context.project_id,
            payload={"plan_sha": sha, "episode_count": len(plan["episodes"])},
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"plan": plan, "uri": str(path)},
            metrics={"episodes": float(len(plan["episodes"]))},
        )
