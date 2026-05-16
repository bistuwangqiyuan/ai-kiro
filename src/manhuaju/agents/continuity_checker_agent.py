"""ContinuityCheckerAgent — cross-episode consistency matrix (REQ-CON-001..010)."""

from __future__ import annotations

from manhuaju.adapters.qa.mock_qa_evaluator_adapter import MockQAEvaluatorAdapter
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent


class ContinuityCheckerAgent(BaseAgent):
    name = "ContinuityCheckerAgent"

    def __init__(self, ctx: AgentContext, *, qa: MockQAEvaluatorAdapter) -> None:
        super().__init__(ctx)
        self.qa = qa

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        # episode_signatures: { episode_id : { char_id : outfit_id } }
        sigs: dict[str, dict[str, str]] = req.inputs["episode_signatures"]
        eps = sorted(sigs.keys())
        matrix: dict[str, dict[str, dict[str, float]]] = {}
        drifted: list[str] = []
        for i, ep_a in enumerate(eps):
            for ep_b in eps[i + 1:]:
                pair_key = f"{ep_a}|{ep_b}"
                matrix[pair_key] = {}
                chars = set(sigs[ep_a].keys()) & set(sigs[ep_b].keys())
                for c in sorted(chars):
                    score = self.qa.cross_episode_arcface(
                        char_id=c,
                        outfit_id_a=sigs[ep_a][c],
                        outfit_id_b=sigs[ep_b][c],
                    )
                    matrix[pair_key][c] = {"arcface": score}
                    if score < 0.92 and c not in drifted:
                        drifted.append(c)
        return AgentRunResponse(
            status="succeeded",
            outputs={"matrix": matrix, "drifted": drifted, "compared": eps},
            metrics={"min_arcface": min(
                (cell["arcface"] for pair in matrix.values() for cell in pair.values()),
                default=1.0,
            )},
        )
