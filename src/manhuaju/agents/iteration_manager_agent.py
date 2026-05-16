"""IterationManagerAgent — failure-mode driven repair loop (REQ-IT-001..010)."""

from __future__ import annotations

from dataclasses import dataclass

from manhuaju.core.agent_base import AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.core.failure_modes import RETRY_BUDGETS, TABLE
from manhuaju.schemas import FailureMode


@dataclass
class RepairPlan:
    failure_mode: FailureMode
    target: str  # shot/scene/episode/project/agent/dialogue/char_refs
    target_id: str
    strategy: str


class IterationManagerAgent(BaseAgent):
    name = "IterationManagerAgent"

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        # Inputs: shot_reports + episode_report + drift_list -> emit plans
        shot_reports = req.inputs.get("shot_reports", [])
        drifted = req.inputs.get("drifted", [])
        plans: list[RepairPlan] = []

        for s in shot_reports:
            if s["verdict"] == "pass":
                continue
            for reason in s["reasons"]:
                fm_id = reason.split(":", 1)[0]
                try:
                    fm = FailureMode(fm_id)
                except ValueError:
                    continue
                strat = TABLE[fm]
                plans.append(
                    RepairPlan(
                        failure_mode=fm,
                        target=strat.target,
                        target_id=s["shot_id"],
                        strategy=strat.name,
                    )
                )

        if drifted:
            for char_id in drifted:
                plans.append(
                    RepairPlan(
                        failure_mode=FailureMode.F003_CONSISTENCY_FACE_LOW,
                        target="char_refs",
                        target_id=char_id,
                        strategy=TABLE[FailureMode.F003_CONSISTENCY_FACE_LOW].name,
                    )
                )

        # apply retry-budget guardrails (T-0506)
        # Group plans by target type and cap.
        capped: list[RepairPlan] = []
        seen_per_target: dict[str, int] = {}
        for p in plans:
            key = f"{p.target}:{p.target_id}"
            n = seen_per_target.get(key, 0)
            cap = RETRY_BUDGETS.get(p.target, 1)
            if n < cap:
                capped.append(p)
                seen_per_target[key] = n + 1
        return AgentRunResponse(
            status="succeeded",
            outputs={
                "plans": [
                    {
                        "failure_mode": p.failure_mode.value,
                        "target": p.target,
                        "target_id": p.target_id,
                        "strategy": p.strategy,
                    }
                    for p in capped
                ]
            },
            metrics={"plans": float(len(capped))},
        )
