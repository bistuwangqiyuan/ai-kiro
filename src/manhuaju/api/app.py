"""FastAPI application skeleton (REQ-API-001..004)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from manhuaju.adapters.db.sqlite_repo import SQLiteRepo
from manhuaju.core.agent_base import AgentContext
from manhuaju.core.budget_service import BudgetService, make_budget
from manhuaju.core.event_bus import InMemoryEventBus
from manhuaju.core.provenance import ProvenanceStore
from manhuaju.core.review_gate import ReviewGate
from manhuaju.core.storage import LocalFSStorage
from manhuaju.core.workflow_config import load_distribution_config, load_workflow_config
from manhuaju.core.workflow_stage import WorkflowStage, emit_workflow_stage
from manhuaju.pipelines.project_flow import ProjectFlowConfig, ProjectPipeline


class ProjectCreateRequest(BaseModel):
    novel_text: str = Field(min_length=10)
    seed: int = 20260516
    episode_count: int = 3
    style_preset_id: str = "cinematic_2d_v1"


class ReviewRequest(BaseModel):
    action: str
    note: str = ""


def create_app(
    *,
    storage_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> FastAPI:
    app = FastAPI(title="Manhuaju Autopilot API", version="1.0.0")
    root = storage_root or Path("./api_data")
    root.mkdir(parents=True, exist_ok=True)
    cfg = config or {}
    wf = load_workflow_config(cfg)
    dist = load_distribution_config(cfg)
    repo = SQLiteRepo(root / "jobs.sqlite")
    review_gate = ReviewGate(mode=wf.mode)

    def _ctx(project_id: str) -> AgentContext:
        base = root / project_id
        return AgentContext(
            storage=LocalFSStorage(base),
            bus=InMemoryEventBus(base / "events.jsonl"),
            budget=BudgetService(make_budget("S")),
            provenance=ProvenanceStore(base / "provenance"),
            config=cfg,
        )

    def _run_project(project_id: str, body: ProjectCreateRequest) -> None:
        repo.set(
            f"project:{project_id}",
            json.dumps({"status": "running", "stage": WorkflowStage.ANALYZE.value}),
        )
        ctx = _ctx(project_id)
        emit_workflow_stage(ctx.bus, project_id=project_id, stage=WorkflowStage.ANALYZE)
        pipe = ProjectPipeline(ctx, redlines=[])
        result = pipe.run(
            ProjectFlowConfig(
                project_id=project_id,
                novel_text=body.novel_text,
                seed=body.seed,
                episode_count=body.episode_count,
                style_preset_id=body.style_preset_id,
                out_dir=root / project_id / "output",
            )
        )
        repo.set(
            f"project:{project_id}",
            json.dumps(
                {
                    "status": result.get("status", "failed"),
                    "stage": WorkflowStage.DISTRIBUTION.value,
                    "manifest": result.get("manifest"),
                },
                ensure_ascii=False,
            ),
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": wf.mode, "platform": dist.default_platform}

    @app.post("/v1/projects")
    def create_project(body: ProjectCreateRequest, bg: BackgroundTasks) -> dict[str, str]:
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        repo.set(
            f"project:{project_id}",
            json.dumps({"status": "queued", "stage": WorkflowStage.ANALYZE.value}),
        )
        bg.add_task(_run_project, project_id, body)
        return {"project_id": project_id, "status": "queued"}

    @app.get("/v1/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        raw = repo.get(f"project:{project_id}")
        if not raw:
            raise HTTPException(status_code=404, detail="project not found")
        return json.loads(raw)

    @app.get("/v1/projects/{project_id}/artefacts")
    def get_artefacts(project_id: str) -> dict[str, Any]:
        manifest_path = root / project_id / "output" / project_id / "99_manifest.json"
        fs_manifest = root / project_id / project_id / "99_manifest.json"
        for p in (manifest_path, fs_manifest):
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        raw = repo.get(f"project:{project_id}")
        if not raw:
            raise HTTPException(status_code=404, detail="project not found")
        data = json.loads(raw)
        return {"manifest": data.get("manifest"), "export_dir": str(root / project_id / "export")}

    @app.post("/v1/projects/{project_id}/review/{episode_id}")
    def review_episode(project_id: str, episode_id: str, body: ReviewRequest) -> dict[str, Any]:
        if wf.mode != "supervised":
            raise HTTPException(status_code=400, detail="review only available in supervised mode")
        return review_gate.apply(project_id, episode_id, body.action, note=body.note)

    @app.post("/v1/webhooks/render")
    def render_webhook(payload: dict[str, Any]) -> dict[str, str]:
        return {"status": "accepted", "task_id": str(payload.get("task_id", ""))}

    app.state.repo = repo
    app.state.review_gate = review_gate
    return app


app = create_app()
