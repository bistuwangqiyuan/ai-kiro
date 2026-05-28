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
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from manhuaju.adapters.db.sqlite_repo import SQLiteRepo
from manhuaju.api.auth import (
    UserStore,
    make_current_user_optional,
    make_current_user_required,
    seed_default_users,
)
from manhuaju.api.project_payload import resolve_project_create
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
from manhuaju.services.video_gallery import (
    VideoGallery,
    publish_project_videos,
    rebind_gallery_to_samples,
    seed_bundled_samples,
    normalize_gallery_play_urls,
    video_to_dict,
)
from manhuaju.utils.paths import config_dir


class AuthCredentials(BaseModel):
    username: str = Field(min_length=5, max_length=128)
    password: str = Field(min_length=6, max_length=128)


class ProjectCreateRequest(BaseModel):
    novel_text: str = Field(min_length=10)
    seed: int = 20260516
    # Default = 1 shortest episode → real generation completes within the
    # 30 min FaaS request_timeout and limits cost per smoke run. Pro users
    # can override either field via the form.
    episode_count: int = 1
    style_preset_id: str = "cinematic_2d_v1"
    genre: str = "ancient"
    target_audience: str = "general"
    episode_duration_s: int = 30
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
        spec = dict(job.project_spec or {})
        # `_project_id` (when present) lets the API enqueue a job that is
        # tracked under a project_id we already returned to the client, so
        # polling /v1/projects/{pid} keeps working across the queue boundary.
        project_id = str(spec.pop("_project_id", "") or "") or f"proj_{uuid.uuid4().hex[:12]}"
        body = ProjectCreateRequest.model_validate(spec)
        _run_project(project_id, body)
        return {"project_id": project_id, "status": "completed"}

    batch_scheduler = BatchScheduler(
        db_path=root / "batch.sqlite",
        executor=_project_executor,
    )
    gallery = VideoGallery(root / "gallery.sqlite")
    users = UserStore(root / "users.sqlite")
    current_user_optional = make_current_user_optional(users)
    current_user_required = make_current_user_required(users)
    # Seed deterministic test accounts eagerly so anonymous TestClient calls and
    # cold container starts both have them available without waiting for the
    # asynchronous startup hook.
    try:
        seed_default_users(users)
    except Exception:  # noqa: BLE001
        pass

    def _get_tos() -> Any:
        from manhuaju.adapters.storage.tos_storage import TOSStorage

        return TOSStorage(settings=settings, local_fallback_root=root / "_tos")

    def _publish_to_gallery(
        project_id: str,
        manifest: dict[str, Any] | None,
        *,
        title: str = "",
        genre: str = "ancient",
        run_mode: str = "",
    ) -> list[dict[str, Any]]:
        if not manifest:
            return []
        try:
            from manhuaju.utils.paths import project_root

            web_dir = project_root() / "web"
            # ``run_mode`` is the bundle mode that produced the manifest.
            # Mock runs have tiny synthetic MP4s so we still want the curated
            # sample fallback to give visitors a watchable preview. Live /
            # hybrid runs must surface the real ``final_mp4`` from the
            # manifest, even if it's smaller than a sample.
            mode = (run_mode or str(cfg.get("mode", "mock"))).lower()
            prefer_real = not mode.startswith("mock")
            published = publish_project_videos(
                gallery=gallery,
                storage_root=root,
                project_id=project_id,
                manifest=manifest,
                title=title or project_id,
                genre=genre,
                tos=_get_tos(),
                web_dir=web_dir,
                prefer_real_render=prefer_real,
            )
            return [video_to_dict(v) for v in published]
        except Exception:  # noqa: BLE001
            return []

    def _backfill_gallery() -> None:
        try:
            for key in repo.scan("project:"):
                pid = key.replace("project:", "")
                if gallery.list_videos(project_id=pid):
                    continue
                raw = repo.get(key)
                if not raw:
                    continue
                data = json.loads(raw)
                if data.get("status") not in ("released", "succeeded", "completed"):
                    continue
                _publish_to_gallery(
                    pid,
                    data.get("manifest"),
                    title=str(data.get("title") or pid),
                    genre=str(data.get("genre") or "ancient"),
                )
        except Exception:  # noqa: BLE001
            pass

    def _ctx(project_id: str) -> AgentContext:
        base = root / project_id
        return AgentContext(
            storage=LocalFSStorage(base),
            bus=InMemoryEventBus(base / "events.jsonl"),
            budget=BudgetService(make_budget("M")),
            provenance=ProvenanceStore(base / "provenance"),
            config=cfg,
        )

    def _build_run_bundle(project_id: str) -> tuple[Any, str]:
        """Try to build a real adapter bundle. Returns (bundle, mode_label).

        ``mode_label`` is one of ``mock``, ``live``, ``hybrid``,
        ``hybrid-degraded`` or ``mock-fallback`` (the last meaning we tried to
        build a real bundle but it failed, so we fell back to mock).
        """
        try:
            from manhuaju.core.adapter_factory import build_bundle

            bundle = build_bundle(storage_root=root / project_id / "output")
            mode_label = str(getattr(bundle, "mode", "mock"))
            engine = str(getattr(bundle, "video_engine", "auto"))
            print(
                f"[run] {project_id} bundle.mode={mode_label} engine={engine} "
                f"render_primary={type(bundle.render_primary).__name__} "
                f"llm={type(bundle.llm).__name__}",
                flush=True,
            )
            return bundle, mode_label
        except Exception as exc:  # noqa: BLE001
            print(
                f"[run] {project_id} build_bundle failed: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            return None, "mock-fallback"

    def _run_project(project_id: str, body: ProjectCreateRequest) -> None:
        meta_raw = repo.get(f"project:{project_id}")
        meta = json.loads(meta_raw) if meta_raw else {}
        title = str(meta.get("title") or project_id)
        owner = meta.get("owner")
        repo.set(
            f"project:{project_id}",
            json.dumps({"status": "running", "stage": WorkflowStage.ANALYZE.value, **meta}),
        )
        ctx = _ctx(project_id)
        emit_workflow_stage(ctx.bus, project_id=project_id, stage=WorkflowStage.ANALYZE)
        bundle, run_mode = _build_run_bundle(project_id)
        pipe = ProjectPipeline(ctx, redlines=[], bundle=bundle)
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
        manifest = result.get("manifest")
        status = result.get("status", "failed")
        gallery_videos: list[dict[str, Any]] = []
        if status in ("released", "succeeded", "completed") and manifest:
            gallery_videos = _publish_to_gallery(
                project_id,
                manifest,
                title=title,
                genre=body.genre,
                run_mode=run_mode,
            )
        repo.set(
            f"project:{project_id}",
            json.dumps(
                {
                    "status": status,
                    "stage": WorkflowStage.DISTRIBUTION.value,
                    "manifest": manifest,
                    "genre": body.genre,
                    "platforms": body.platforms,
                    "title": title,
                    "owner": owner,
                    "gallery_videos": gallery_videos,
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

    @app.get("/v1/diagnostics/bundle")
    def diagnostics_bundle() -> dict[str, Any]:
        """Inspect what the runtime adapter bundle looks like for new projects.

        Useful when a project completes suspiciously fast (mock-style) on a
        hybrid deployment — this endpoint reveals which class is actually
        wired into ``render_primary`` etc., so you can tell whether silent
        ``mock_fallback`` is being injected.
        """
        bundle, mode_label = _build_run_bundle("__diag__")
        if bundle is None:
            return {"ok": False, "mode": mode_label, "error": "build_bundle failed"}

        def _cls(obj: Any) -> str:
            return type(obj).__name__ if obj is not None else ""

        return {
            "ok": True,
            "mode": mode_label,
            "video_engine": str(getattr(bundle, "video_engine", "")),
            "adapters": {
                "llm": _cls(bundle.llm),
                "llm_native": _cls(bundle.llm_native),
                "render_primary": _cls(bundle.render_primary),
                "render_fallback": _cls(bundle.render_fallback),
                "image": _cls(bundle.image),
                "image_variant": _cls(bundle.image_variant),
                "tts": _cls(bundle.tts),
                "music": _cls(bundle.music),
                "sfx": _cls(bundle.sfx),
                "qa": _cls(bundle.qa),
                "vlm": _cls(bundle.vlm),
                "moderation": _cls(bundle.moderation),
                "embedding": _cls(bundle.embedding),
                "storage_tos": _cls(bundle.storage_tos),
                "manhuaju_video_generator": _cls(bundle.manhuaju_video_generator),
            },
            "settings": {
                "has_any_llm": settings.has_any_llm,
                "has_anthropic": settings.has_anthropic,
                "has_xiaoyunque": settings.has_xiaoyunque,
                "has_tos": settings.has_tos,
            },
        }

    @app.post("/v1/projects")
    def create_project(
        body: dict[str, Any],
        bg: BackgroundTasks,
        current_user: dict[str, Any] | None = Depends(current_user_optional),
    ) -> dict[str, str]:
        try:
            resolved = resolve_project_create(body)
            req = ProjectCreateRequest.model_validate(resolved)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        owner = current_user.get("username") if current_user else None
        repo.set(
            f"project:{project_id}",
            json.dumps(
                {
                    "status": "queued",
                    "stage": WorkflowStage.ANALYZE.value,
                    "mode": body.get("mode"),
                    "title": body.get("title"),
                    "owner": owner,
                }
            ),
        )
        # When the deployment has a real adapter bundle (live / hybrid +
        # provider keys present), real Xiaoyunque rendering takes 5-15 min
        # per episode. FastAPI BackgroundTasks live inside the FaaS request
        # context and may be killed when the function instance is recycled,
        # so we instead enqueue a batch job and let the cron-driven
        # ``worker_tick`` (1 min cadence, 1500 s budget per tick) drain it.
        # In mock mode the job finishes in ~1 s so bg.add_task is fine and
        # avoids the 1 min cron lag.
        sysmode = str(cfg.get("mode", "mock")).lower()
        use_queue = sysmode in ("live", "hybrid") and (
            settings.has_xiaoyunque or settings.has_any_llm
        )
        spec = req.model_dump()
        spec["_project_id"] = project_id
        if use_queue:
            try:
                job_id = batch_scheduler.enqueue(
                    template_id=str(resolved.get("template_id") or "default"),
                    project_spec=spec,
                )
                # Best-effort kick: if the worker_tick is idle this drains
                # the new job immediately instead of waiting up to 60 s for
                # the next cron beat.
                bg.add_task(batch_scheduler.run_next)
                return {
                    "project_id": project_id,
                    "status": "queued",
                    "owner": owner or "",
                    "job_id": job_id,
                    "executor": "batch",
                }
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[create_project] batch enqueue failed for {project_id}: "
                    f"{type(exc).__name__}: {exc}; falling back to bg.add_task",
                    flush=True,
                )
        bg.add_task(_run_project, project_id, req)
        return {
            "project_id": project_id,
            "status": "queued",
            "owner": owner or "",
            "executor": "background_task",
        }

    @app.get("/v1/projects")
    def list_projects(
        limit: int = 100,
        mine: bool = False,
        current_user: dict[str, Any] | None = Depends(current_user_optional),
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        try:
            keys = getattr(repo, "scan", lambda *_: [])("project:")
            for k in list(keys)[:limit]:
                raw = repo.get(k)
                if raw:
                    items.append({"project_id": k.replace("project:", ""), **json.loads(raw)})
        except Exception:  # noqa: BLE001
            pass
        if mine:
            if not current_user:
                raise HTTPException(status_code=401, detail="login_required")
            uname = current_user.get("username")
            items = [it for it in items if it.get("owner") == uname]
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

    # ---- auth endpoints ----
    @app.post("/v1/auth/register")
    def auth_register(body: AuthCredentials) -> dict[str, Any]:
        try:
            user = users.register(body.username, body.password)
        except ValueError as exc:
            code = str(exc)
            if code == "user_exists":
                raise HTTPException(status_code=409, detail="user_exists") from exc
            raise HTTPException(status_code=400, detail=code) from exc
        sess = users.create_session(user.username)
        return {
            "user": user.to_public(),
            "token": sess.token,
            "expires_at": sess.expires_at,
        }

    @app.post("/v1/auth/login")
    def auth_login(body: AuthCredentials) -> dict[str, Any]:
        try:
            user = users.verify_credentials(body.username, body.password)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="invalid_credentials") from exc
        sess = users.create_session(user.username)
        return {
            "user": user.to_public(),
            "token": sess.token,
            "expires_at": sess.expires_at,
        }

    @app.post("/v1/auth/logout")
    def auth_logout(
        current_user: dict[str, Any] = Depends(current_user_required),
    ) -> dict[str, str]:
        token = str(current_user.get("token") or "")
        users.delete_session(token)
        return {"status": "ok"}

    @app.get("/v1/auth/me")
    def auth_me(
        current_user: dict[str, Any] = Depends(current_user_required),
    ) -> dict[str, Any]:
        return {
            "username": current_user.get("username"),
            "created_at": current_user.get("created_at"),
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

    @app.get("/v1/whitepaper/anchors")
    def get_whitepaper_anchors() -> dict[str, Any]:
        """KPI sidebar for Pro console — bundled anchors (no research/ dep in image)."""
        path = config_dir() / "whitepaper-anchors.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {
            "cost_p95": 80.0,
            "episode_p95_s": 3600.0,
            "arcface_lead": 0.92,
            "seven_dim_pass": 0.55,
            "episodes_per_hour": 8.0,
        }

    @app.get("/v1/modes")
    def list_modes() -> dict[str, Any]:
        from manhuaju.api.mode_router import ModeRouter

        router = ModeRouter.load()
        return {
            name: {
                "locked_params": list(p.locked_params),
                "defaults": p.defaults,
                "exposed_params": list(p.exposed_params),
            }
            for name, p in router.presets.items()
        }

    @app.get("/v1/versions/{project_id}")
    def list_versions(project_id: str) -> dict[str, Any]:
        return {"versions": version_store.list_by_project(project_id)}

    @app.post("/v1/webhooks/render")
    def render_webhook(payload: dict[str, Any]) -> dict[str, str]:
        return {"status": "accepted", "task_id": str(payload.get("task_id", ""))}

    # ---- video gallery ----
    @app.get("/v1/gallery")
    def list_gallery(limit: int = 100, project_id: str | None = None) -> dict[str, Any]:
        videos = gallery.list_videos(limit=limit, project_id=project_id)
        return {"videos": [video_to_dict(v) for v in videos], "count": len(videos)}

    @app.get("/v1/gallery/{video_id}")
    def get_gallery_video(video_id: str) -> dict[str, Any]:
        v = gallery.get(video_id)
        if not v:
            raise HTTPException(status_code=404, detail="video not found")
        return video_to_dict(v)

    @app.get("/media/videos/{video_id}")
    def stream_gallery_video(video_id: str) -> Any:
        from fastapi.responses import FileResponse

        v = gallery.get(video_id)
        if not v:
            raise HTTPException(status_code=404, detail="video not found")
        path = Path(v.local_video)
        if path.is_file():
            return FileResponse(path, media_type="video/mp4", filename=f"{v.episode_id}.mp4")
        if v.video_url.startswith("http"):
            from fastapi.responses import RedirectResponse

            return RedirectResponse(v.video_url)
        raise HTTPException(status_code=404, detail="video file missing")

    @app.get("/media/covers/{video_id}")
    def stream_gallery_cover(video_id: str) -> Any:
        from fastapi.responses import FileResponse

        v = gallery.get(video_id)
        if not v or not v.local_cover:
            raise HTTPException(status_code=404, detail="cover not found")
        path = Path(v.local_cover)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="cover file missing")
        return FileResponse(path, media_type="image/jpeg")

    @app.on_event("startup")
    def _startup_gallery() -> None:
        from manhuaju.utils.paths import project_root

        web_dir = project_root() / "web"
        for legacy_id in ("sample_ep01", "sample_ep02", "sample_ep03"):
            gallery.delete(legacy_id)
        seed_bundled_samples(gallery=gallery, web_dir=web_dir)
        rebind_gallery_to_samples(gallery=gallery, web_dir=web_dir)
        normalize_gallery_play_urls(gallery=gallery)
        _backfill_gallery()

    @app.on_event("startup")
    def _startup_auth() -> None:
        try:
            seed_default_users(users)
        except Exception:  # noqa: BLE001
            pass
        try:
            users.purge_expired()
        except Exception:  # noqa: BLE001
            pass

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

        @app.get("/guide")
        def user_guide() -> Any:
            return FileResponse(web_dir / "guide.html")

        @app.get("/gallery")
        def video_gallery_page() -> Any:
            return FileResponse(web_dir / "gallery.html")

        @app.get("/login")
        def login_page() -> Any:
            return FileResponse(web_dir / "login.html")

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
    app.state.gallery = gallery
    app.state.users = users
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
