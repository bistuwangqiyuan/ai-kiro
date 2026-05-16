"""BaseAgent infrastructure (design §3 Component View).

Every Agent shares: input validation -> inner planner (LLM) -> tools (Adapters)
-> output synthesizer -> schema validation -> provenance + event emission.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from manhuaju.core.budget_service import BudgetService
from manhuaju.core.event_bus import InMemoryEventBus
from manhuaju.core.provenance import ProvenanceStore
from manhuaju.core.storage import LocalFSStorage
from manhuaju.utils.logging import log_event


@dataclass
class TraceContext:
    project_id: str
    episode_id: str | None = None
    shot_id: str | None = None
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class BudgetSpec:
    tokens: int = 0
    seconds: int = 0
    credits: int = 0


@dataclass
class AgentRunRequest:
    inputs: dict[str, Any]
    context: TraceContext
    budgets: BudgetSpec = field(default_factory=BudgetSpec)
    seed: int | None = None


@dataclass
class AgentRunResponse:
    status: str  # "succeeded" | "failed" | "degraded"
    outputs: dict[str, Any]
    metrics: dict[str, float]
    next_hint: str | None = None


@dataclass
class AgentContext:
    """Shared services bag passed to every Agent."""

    storage: LocalFSStorage
    bus: InMemoryEventBus
    budget: BudgetService
    provenance: ProvenanceStore
    config: dict[str, Any]


class BaseAgent:
    name: str = "BaseAgent"
    version: str = "v1"

    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    # subclasses override .run()
    def run(self, req: AgentRunRequest) -> AgentRunResponse:  # pragma: no cover
        raise NotImplementedError

    # convenience wrapper that emits structured events around a run
    def run_with_telemetry(self, req: AgentRunRequest) -> AgentRunResponse:
        start = time.perf_counter()
        log_event(
            "agent.start",
            agent=self.name,
            project_id=req.context.project_id,
            episode_id=req.context.episode_id,
            shot_id=req.context.shot_id,
            trace_id=req.context.trace_id,
        )
        try:
            resp = self.run(req)
        except Exception as e:
            log_event(
                "agent.error",
                agent=self.name,
                error=str(e),
                trace_id=req.context.trace_id,
            )
            raise
        elapsed = time.perf_counter() - start
        log_event(
            "agent.end",
            agent=self.name,
            status=resp.status,
            elapsed_s=round(elapsed, 3),
            metrics=resp.metrics,
            trace_id=req.context.trace_id,
        )
        # Charge minimal budget so utilisation reflects work
        self.ctx.budget.charge(seconds=int(elapsed) + 1, tokens=req.budgets.tokens)
        return resp
