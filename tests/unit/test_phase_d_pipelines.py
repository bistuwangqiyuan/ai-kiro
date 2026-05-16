"""Phase D smoke gate: full project pipeline produces real episode mp4s."""

from __future__ import annotations

from pathlib import Path

from manhuaju.core.agent_base import AgentContext
from manhuaju.core.budget_service import BudgetService, make_budget
from manhuaju.core.event_bus import InMemoryEventBus
from manhuaju.core.provenance import ProvenanceStore
from manhuaju.core.storage import LocalFSStorage
from manhuaju.pipelines.project_flow import ProjectFlowConfig, ProjectPipeline


def test_project_pipeline_three_episodes(tmp_path: Path) -> None:
    ctx = AgentContext(
        storage=LocalFSStorage(tmp_path / "fs"),
        bus=InMemoryEventBus(tmp_path / "events.jsonl"),
        budget=BudgetService(make_budget("S")),
        provenance=ProvenanceStore(tmp_path / "prov"),
        config={},
    )
    cfg = ProjectFlowConfig(
        project_id="proj_test",
        novel_text="林云雀和陈翊在天港遇见了苏决。" * 80,
        seed=42,
        episode_count=3,
        out_dir=tmp_path / "out",
    )
    pipe = ProjectPipeline(ctx, redlines=["xxxnonexistent"])
    res = pipe.run(cfg)
    assert res["status"] == "released"
    eps = res["manifest"]["episodes"]
    assert len(eps) == 3
    for ep in eps:
        p = Path(ep["final_mp4"])
        assert p.exists(), f"missing {p}"
        assert p.stat().st_size > 1024
    # Provenance chain still intact
    assert ctx.provenance.verify() is True


def test_pipeline_event_bus_emits_state_transitions(tmp_path: Path) -> None:
    ctx = AgentContext(
        storage=LocalFSStorage(tmp_path / "fs"),
        bus=InMemoryEventBus(tmp_path / "events.jsonl"),
        budget=BudgetService(make_budget("S")),
        provenance=ProvenanceStore(tmp_path / "prov"),
        config={},
    )
    cfg = ProjectFlowConfig(
        project_id="proj_state",
        novel_text="一个简短的样例。" * 100,
        seed=7,
        episode_count=2,
        out_dir=tmp_path / "out",
    )
    pipe = ProjectPipeline(ctx, redlines=[])
    pipe.run(cfg)
    states = [
        e.payload.get("state")
        for e in ctx.bus.events
        if e.subject == "manhuaju.event.project.state"
    ]
    assert "Accepted" in states
    assert "Released" in states
