"""BatchJobScheduler — docx 八节「批量生产 / 模板复用 / 定时上传」.

特性：
- 批量任务：一次提交多个 ``ProjectSpec`` 进队列；
- 模板复用：同一 template_id 多次 instantiate（题材/角色变更）；
- 定时上传：APScheduler 定时触发 DistributionAgent；
- 持久化：SQLite (jobs / schedules 表)；
- 与 FastAPI ``/v1/batch`` 端点对接。

graceful fallback：未装 APScheduler → 退化到同步执行。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-not-found]
    from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-not-found]

    HAS_APS = True
except ImportError:
    HAS_APS = False


@dataclass
class BatchJob:
    job_id: str
    template_id: str
    project_spec: dict[str, Any]
    status: str = "queued"        # queued | running | succeeded | failed
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass
class Schedule:
    schedule_id: str
    cron: str                     # e.g. "0 8 * * *"
    action: str                   # generate | distribute | report
    params: dict[str, Any]
    enabled: bool = True


class BatchScheduler:
    """Persistent batch & cron-job manager."""

    def __init__(self, *, db_path: str | Path, executor=None) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._executor = executor          # callable(BatchJob) -> dict
        self._lock = threading.Lock()
        self._scheduler: Any | None = None
        self._init_db()
        if HAS_APS:
            self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
            self._scheduler.start(paused=False)
            self._restore_schedules()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db) as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS manhuaju_batch_jobs (
                    job_id TEXT PRIMARY KEY,
                    template_id TEXT NOT NULL,
                    project_spec TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    result TEXT NOT NULL,
                    note TEXT NOT NULL
                )"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS manhuaju_batch_schedules (
                    schedule_id TEXT PRIMARY KEY,
                    cron TEXT NOT NULL,
                    action TEXT NOT NULL,
                    params TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                )"""
            )

    # ===== Job API =====
    def enqueue(self, template_id: str, project_spec: dict[str, Any]) -> str:
        job = BatchJob(
            job_id=str(uuid.uuid4()),
            template_id=template_id,
            project_spec=project_spec,
        )
        with self._lock, sqlite3.connect(self._db) as c:
            c.execute(
                """INSERT INTO manhuaju_batch_jobs
                   (job_id, template_id, project_spec, status,
                    created_at, started_at, finished_at, result, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job.job_id,
                    job.template_id,
                    json.dumps(job.project_spec, ensure_ascii=False),
                    job.status,
                    job.created_at,
                    job.started_at,
                    job.finished_at,
                    json.dumps(job.result, ensure_ascii=False),
                    job.note,
                ),
            )
        return job.job_id

    def list_jobs(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with sqlite3.connect(self._db) as c:
            cur = c.execute(
                "SELECT * FROM manhuaju_batch_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        out = []
        for r in rows:
            rec = dict(zip(cols, r, strict=False))
            rec["project_spec"] = json.loads(rec["project_spec"])
            rec["result"] = json.loads(rec["result"])
            out.append(rec)
        return out

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self._db) as c:
            cur = c.execute(
                "SELECT * FROM manhuaju_batch_jobs WHERE job_id = ?", (job_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
        rec = dict(zip(cols, row, strict=False))
        rec["project_spec"] = json.loads(rec["project_spec"])
        rec["result"] = json.loads(rec["result"])
        return rec

    def run_next(self) -> str | None:
        """Pull one queued job and execute it via injected executor."""
        if self._executor is None:
            return None
        with self._lock, sqlite3.connect(self._db) as c:
            row = c.execute(
                "SELECT job_id FROM manhuaju_batch_jobs WHERE status = 'queued' "
                "ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            job_id = row[0]
            c.execute(
                "UPDATE manhuaju_batch_jobs SET status='running', started_at=? WHERE job_id=?",
                (time.time(), job_id),
            )
        try:
            job_dict = self.get_job(job_id) or {}
            job = BatchJob(
                job_id=job_dict["job_id"],
                template_id=job_dict["template_id"],
                project_spec=job_dict["project_spec"],
                status="running",
                created_at=job_dict["created_at"],
                started_at=job_dict["started_at"],
            )
            result = self._executor(job)
            self._finish(job_id, success=True, result=result)
        except Exception as e:  # noqa: BLE001
            self._finish(job_id, success=False, result={"error": str(e)})
        return job_id

    def _finish(self, job_id: str, *, success: bool, result: dict[str, Any]) -> None:
        with self._lock, sqlite3.connect(self._db) as c:
            c.execute(
                "UPDATE manhuaju_batch_jobs SET status=?, finished_at=?, result=? WHERE job_id=?",
                (
                    "succeeded" if success else "failed",
                    time.time(),
                    json.dumps(result, ensure_ascii=False),
                    job_id,
                ),
            )

    # ===== Schedule API =====
    def add_schedule(self, cron: str, action: str, params: dict[str, Any]) -> str:
        sched = Schedule(
            schedule_id=str(uuid.uuid4()), cron=cron, action=action, params=params
        )
        with self._lock, sqlite3.connect(self._db) as c:
            c.execute(
                """INSERT INTO manhuaju_batch_schedules
                   (schedule_id, cron, action, params, enabled)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    sched.schedule_id,
                    sched.cron,
                    sched.action,
                    json.dumps(sched.params, ensure_ascii=False),
                    1,
                ),
            )
        if self._scheduler is not None and HAS_APS:
            self._scheduler.add_job(
                self._dispatch_schedule,
                CronTrigger.from_crontab(cron),
                args=(sched.schedule_id, action, sched.params),
                id=sched.schedule_id,
                replace_existing=True,
            )
        return sched.schedule_id

    def _restore_schedules(self) -> None:
        if not HAS_APS:
            return
        with sqlite3.connect(self._db) as c:
            rows = c.execute(
                "SELECT schedule_id, cron, action, params, enabled "
                "FROM manhuaju_batch_schedules WHERE enabled = 1"
            ).fetchall()
        for sid, cron, action, params, _enabled in rows:
            try:
                self._scheduler.add_job(
                    self._dispatch_schedule,
                    CronTrigger.from_crontab(cron),
                    args=(sid, action, json.loads(params)),
                    id=sid,
                    replace_existing=True,
                )
            except (ValueError, KeyError):
                continue

    def _dispatch_schedule(self, schedule_id: str, action: str, params: dict[str, Any]) -> None:
        if self._executor is None:
            return
        # For "generate" actions, enqueue a job from the schedule's params
        if action == "generate":
            self.enqueue(template_id=params.get("template_id", "default"), project_spec=params)
            return
        # For "distribute"/"report" the params should target the executor directly
        try:
            job = BatchJob(
                job_id=schedule_id,
                template_id=action,
                project_spec=params,
                status="running",
                started_at=time.time(),
            )
            self._executor(job)
        except Exception:  # noqa: BLE001
            pass

    def shutdown(self) -> None:
        if self._scheduler is not None and HAS_APS:
            self._scheduler.shutdown(wait=False)


def job_to_dict(job: BatchJob) -> dict[str, Any]:
    return asdict(job)
