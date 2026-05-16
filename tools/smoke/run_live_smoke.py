"""Run a tiny live pipeline with progress prints (bypass pytest buffering).

Writes one episode end-to-end through the AdapterFactory in `hybrid` mode.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def main() -> int:
    from manhuaju.core.adapter_factory import build_bundle
    from manhuaju.core.agent_base import AgentContext
    from manhuaju.core.budget_service import BudgetService, make_budget
    from manhuaju.core.event_bus import InMemoryEventBus
    from manhuaju.core.provenance import ProvenanceStore
    from manhuaju.core.storage import LocalFSStorage
    from manhuaju.pipelines.project_flow import ProjectFlowConfig, ProjectPipeline

    cfg_path = ROOT / "tests" / "live_one_episode" / "input" / "pilot_config.yaml"
    novel_path = ROOT / "tests" / "e2e_three_episodes" / "input" / "sample_novel.md"

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    novel = novel_path.read_text(encoding="utf-8")
    project_id = "live_smoke"
    seed = int(cfg["project"]["seed"])
    cfg_block = cfg.get("config", {})
    mock_block = cfg.get("mock", {})

    out = ROOT / "tools" / "smoke" / "_live_smoke_run"
    out.mkdir(parents=True, exist_ok=True)
    storage_root = out / "fs"
    bus_journal = out / "events.jsonl"
    prov_root = out / "prov"

    log("building AgentContext")
    ctx = AgentContext(
        storage=LocalFSStorage(storage_root),
        bus=InMemoryEventBus(bus_journal),
        budget=BudgetService(make_budget("S")),
        provenance=ProvenanceStore(prov_root),
        config={"reports_dir": str(out / "reports")},
    )

    mode = os.getenv("MANHUAJU_LIVE_MODE", "hybrid")
    log(f"build_bundle mode={mode}")
    t0 = time.time()
    bundle = build_bundle(storage_root=storage_root, mode_override=mode, redlines=[])
    log(f"  bundle.mode={bundle.mode}  llm={type(bundle.llm).__name__}  "
        f"video={type(bundle.render_primary).__name__}  ({time.time() - t0:.1f}s)")

    pipe = ProjectPipeline(ctx, redlines=[], bundle=bundle)
    flow_cfg = ProjectFlowConfig(
        project_id=project_id,
        novel_text=novel,
        seed=seed,
        episode_count=1,
        style_preset_id=cfg_block.get("style_preset_id", "cinematic_2d_v1"),
        aspect_ratio=cfg_block.get("aspect_ratio", "16:9"),
        resolution=mock_block.get("resolution", "720p"),
        fps=int(mock_block.get("fps", 12)),
        max_repairs=int(mock_block.get("max_repairs", 1)),
        out_dir=out,
    )

    def hook(ev: object) -> None:
        log(f"  EVT {getattr(ev, 'subject', '?')} {getattr(ev, 'payload', '')}")

    ctx.bus.subscribe("manhuaju.event.project.state", hook)
    ctx.bus.subscribe("manhuaju.event.episode.state", hook)

    log("running pipeline …")
    t0 = time.time()
    res = pipe.run(flow_cfg)
    dt = time.time() - t0
    log(f"pipeline finished status={res.get('status')} runtime={dt:.1f}s")

    summary = bundle.cost.summary()
    log(f"cost summary: rmb={summary['rmb']:.4f} calls={summary['calls']}")
    return 0 if res.get("status") == "released" else 1


if __name__ == "__main__":
    raise SystemExit(main())
