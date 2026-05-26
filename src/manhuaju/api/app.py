"""FastAPI application — v4 console-ready endpoints.

v4 新增端点（docx 十节「web 控制台」铺垫）:
- GET  /health                           — 报告 mode + provider 能力图（带掩码 key）
- POST /v1/projects                      — 启动一个项目
- GET  /v1/projects/{id}                 — 项目状态
- GET  /v1/projects/{id}/artefacts       — 制品 manifest
- POST /v1/projects/{id}/review/{ep}     — 评审动作 (supervised 模式)
- GET  /v1/projects                      — 列出最近项目（控制台用）
- POST /v1/novels                        — 调 NovelWriterAgent 生成小说
- POST /v1/batch/jobs                    — 创建批量任务
- GET  /v1/batch/jobs                    — 列出批量任务
- POST /v1/batch/schedules               — 创建定时任务
- GET  /v1/genres                        — 题材预设
- GET  /v1/platforms                     — 平台规格
- GET  /v1/kpi                           — 当前 KPI 阈值
- GET  /v1/versions/{project_id}         — 版本回滚清单
- POST /v1/webhooks/render               — 渲染回调（小云雀异步）
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from manhuaju.adapters.db.sqlite_repo import SQLiteRepo
from manhuaju.core.agent_base import AgentContext
from manhuaju.core.asset_store import VersionStore
from manhuaju.core.budget_service import BudgetService, make_budget
from manhuaju.core.event_bus import InMemoryEventBus
from manhuaju.core.provenance import ProvenanceStore
from manhuaju.core.provider_settings import get_provider_settings
from manhuaju.core.review_gate import ReviewGate
from manhuaju.core.storage import LocalFSStorage
from manhuaju.core.workflow_config import load_distribution_config, load_workflow_config
from manhuaju.core.workflow_stage import WorkflowStage, emit_workflow_stage
from manhuaju.pipelines.project_flow import ProjectFlowConfig, ProjectPipeline
from manhuaju.services.batch_scheduler import BatchScheduler
from manhuaju.utils.paths import config_dir


class ProjectCreateRequest(BaseModel):
    novel_text: str = Field(min_length=10)
    seed: int = 20260516
    episode_count: int = 3
    style_preset_id: str = "cinematic_2d_v1"
    genre: str = "ancient"
    target_audience: str = "general"
    episode_duration_s: int = 75
    template_id: str | None = None
    platforms: list[str] = Field(default_factory=lambda: ["douyin", "kuaishou", "weixin"])


class ReviewRequest(BaseModel):
    action: str
    note: str = ""


class NovelCreateRequest(BaseModel):
    mode: str = Field(default="generate", pattern="^(generate|continuation|style_transfer)$")
    prompt: str = ""
    original_text: str = ""
    target_chars: int = 12000
    n_chapters: int = 12
    n_more_chapters: int = 3
    genre: str = "ancient"
    target_genre: str = "modern"
    target_style: str = "现代都市轻松向"


class BatchJobCreateRequest(BaseModel):
    template_id: str
    project_spec: dict[str, Any]


class ScheduleCreateRequest(BaseModel):
    cron: str
    action: str = "generate"
    params: dict[str, Any]


def create_app(
    *,
    storage_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> FastAPI:
    app = FastAPI(title="Manhuaju Autopilot API", version="4.0.0")
    root = storage_root or Path("./api_data")
    root.mkdir(parents=True, exist_ok=True)
    cfg = config or _load_system_config()
    wf = load_workflow_config(cfg)
    dist = load_distribution_config(cfg)
    repo = SQLiteRepo(root / "jobs.sqlite")
    review_gate = ReviewGate(mode=wf.mode)
    version_store = VersionStore(root / "versions.sqlite")
    settings = get_provider_settings(refresh=True)

    def _project_executor(job: Any) -> dict[str, Any]:
        body = ProjectCreateRequest.model_validate(job.project_spec)
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        _run_project(project_id, body)
        return {"project_id": project_id, "status": "completed"}

    batch_scheduler = BatchScheduler(
        db_path=root / "batch.sqlite",
        executor=_project_executor,
    )

    def _ctx(project_id: str) -> AgentContext:
        base = root / project_id
        return AgentContext(
            storage=LocalFSStorage(base),
            bus=InMemoryEventBus(base / "events.jsonl"),
            budget=BudgetService(make_budget("M")),
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
                    "genre": body.genre,
                    "platforms": body.platforms,
                },
                ensure_ascii=False,
            ),
        )

    # ====================== Endpoints ======================

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": app.version,
            "mode": wf.mode,
            "default_platform": dist.default_platform,
            "system_mode": str(cfg.get("mode", "mock")),
            "providers": settings.summary(),
            "fast_path_ready": (
                settings.has_xiaoyunque
                and settings.has_tos
                and settings.has_any_llm
            ),
        }

    @app.post("/v1/projects")
    def create_project(body: ProjectCreateRequest, bg: BackgroundTasks) -> dict[str, str]:
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        repo.set(
            f"project:{project_id}",
            json.dumps({"status": "queued", "stage": WorkflowStage.ANALYZE.value}),
        )
        bg.add_task(_run_project, project_id, body)
        return {"project_id": project_id, "status": "queued"}

    @app.get("/v1/projects")
    def list_projects(limit: int = 100) -> dict[str, Any]:
        items = []
        try:
            # SQLiteRepo has `.scan` if implemented; else iterate file
            keys = getattr(repo, "scan", lambda *_: [])("project:")
            for k in list(keys)[:limit]:
                raw = repo.get(k)
                if raw:
                    items.append({"project_id": k.replace("project:", ""), **json.loads(raw)})
        except Exception:  # noqa: BLE001
            pass
        return {"projects": items, "count": len(items)}

    @app.get("/v1/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        raw = repo.get(f"project:{project_id}")
        if not raw:
            raise HTTPException(status_code=404, detail="project not found")
        return json.loads(raw)

    @app.get("/v1/projects/{project_id}/artefacts")
    def get_artefacts(project_id: str) -> dict[str, Any]:
        candidates = [
            root / project_id / "output" / project_id / "99_manifest.json",
            root / project_id / project_id / "99_manifest.json",
        ]
        for p in candidates:
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

    # ---- v4 novel writer ----
    @app.post("/v1/novels")
    def create_novel(body: NovelCreateRequest) -> dict[str, Any]:
        from manhuaju.agents.novel_writer_agent import NovelWriterAgent
        from manhuaju.core.adapter_factory import build_bundle

        project_id = f"novel_{uuid.uuid4().hex[:8]}"
        ctx = _ctx(project_id)
        bundle = build_bundle(storage_root=root / project_id / "output")
        agent = NovelWriterAgent(ctx, llm_native=bundle.llm_native, llm=bundle.llm)
        from manhuaju.core.agent_base import AgentRunRequest, BudgetSpec, TraceContext

        req = AgentRunRequest(
            inputs=body.model_dump(),
            context=TraceContext(project_id=project_id),
            budgets=BudgetSpec(tokens=16000, seconds=120),
        )
        resp = agent.run_with_telemetry(req)
        return {"project_id": project_id, "status": resp.status, **resp.outputs}

    # ---- v4 batch + schedule ----
    @app.post("/v1/batch/jobs")
    def create_batch_job(body: BatchJobCreateRequest) -> dict[str, str]:
        job_id = batch_scheduler.enqueue(body.template_id, body.project_spec)
        return {"job_id": job_id, "status": "queued"}

    @app.get("/v1/batch/jobs")
    def list_batch_jobs(limit: int = 100) -> dict[str, Any]:
        jobs = batch_scheduler.list_jobs(limit=limit)
        return {"jobs": jobs, "count": len(jobs)}

    @app.get("/v1/batch/jobs/{job_id}")
    def get_batch_job(job_id: str) -> dict[str, Any]:
        rec = batch_scheduler.get_job(job_id)
        if not rec:
            raise HTTPException(status_code=404, detail="job not found")
        return rec

    @app.post("/v1/batch/schedules")
    def create_schedule(body: ScheduleCreateRequest) -> dict[str, str]:
        sid = batch_scheduler.add_schedule(body.cron, body.action, body.params)
        return {"schedule_id": sid, "status": "active"}

    # Internal worker tick — called by VeFaaS timer trigger (cron) to drain the
    # batch queue without a separate worker function. Replaces manhuaju-worker
    # (which we cannot afford on the current memory quota).
    @app.post("/v1/internal/worker/tick")
    def worker_tick(event: dict[str, Any] | None = None) -> dict[str, Any]:
        import os
        import time

        started = time.time()
        budget_s = float(os.getenv("MANHUAJU_BURST_BUDGET_S", "1500"))
        burst = int(os.getenv("MANHUAJU_BURST_JOBS", "1"))
        ran: list[str] = []
        errors: list[str] = []
        for _ in range(max(1, burst)):
            if time.time() - started > budget_s:
                break
            try:
                jid = batch_scheduler.run_next()
                if jid is None:
                    break
                ran.append(jid)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
                continue
        return {
            "ok": not errors,
            "ran": ran,
            "count": len(ran),
            "errors": errors,
            "elapsed_s": round(time.time() - started, 2),
            "event": str(event)[:200] if event else None,
        }

    # ---- v4 config endpoints (web 控制台读取) ----
    @app.get("/v1/genres")
    def list_genres() -> dict[str, Any]:
        return _load_yaml("genre-presets.yaml")

    @app.get("/v1/platforms")
    def list_platforms() -> dict[str, Any]:
        return _load_yaml("distribution-platforms.yaml")

    @app.get("/v1/emotions")
    def list_emotions() -> dict[str, Any]:
        return _load_yaml("emotion-library.yaml")

    @app.get("/v1/actions")
    def list_actions() -> dict[str, Any]:
        return _load_yaml("action-library.yaml")

    @app.get("/v1/kpi")
    def get_kpi() -> dict[str, Any]:
        return _load_yaml("kpi.yaml")

    @app.get("/v1/versions/{project_id}")
    def list_versions(project_id: str) -> dict[str, Any]:
        return {"versions": version_store.list_by_project(project_id)}

    @app.post("/v1/webhooks/render")
    def render_webhook(payload: dict[str, Any]) -> dict[str, str]:
        return {"status": "accepted", "task_id": str(payload.get("task_id", ""))}

    # ---- console (静态文件) ----
    from manhuaju.utils.paths import project_root

    web_dir = project_root() / "web"
    if web_dir.exists():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        app.mount("/console", StaticFiles(directory=str(web_dir), html=True), name="console")

        @app.get("/")
        def root_redirect() -> Any:
            return FileResponse(web_dir / "index.html")

    # ---- shutdown ----
    @app.on_event("shutdown")
    def _shutdown() -> None:  # noqa: D401
        try:
            batch_scheduler.shutdown()
        except Exception:  # noqa: BLE001
            pass

    app.state.repo = repo
    app.state.review_gate = review_gate
    app.state.batch_scheduler = batch_scheduler
    app.state.version_store = version_store
    return app


def _load_system_config() -> dict[str, Any]:
    path = config_dir() / "system.yaml"
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def _load_yaml(name: str) -> dict[str, Any]:
    path = config_dir() / name
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


app = create_app()
