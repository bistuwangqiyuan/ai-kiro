"""Gate the BatchScheduler list/get endpoints — the cursor.description fix."""

from __future__ import annotations

from pathlib import Path

import pytest

from manhuaju.services.batch_scheduler import BatchScheduler


@pytest.fixture()
def scheduler(tmp_path: Path) -> BatchScheduler:
    return BatchScheduler(db_path=tmp_path / "batch.sqlite")


def test_enqueue_and_get_round_trip(scheduler: BatchScheduler) -> None:
    job_id = scheduler.enqueue(
        template_id="cdrama_classic",
        project_spec={"_project_id": "proj_test", "novel_text": "x" * 30},
    )
    rec = scheduler.get_job(job_id)
    assert rec is not None
    assert rec["job_id"] == job_id
    assert rec["template_id"] == "cdrama_classic"
    assert rec["status"] == "queued"
    assert rec["project_spec"]["_project_id"] == "proj_test"
    assert isinstance(rec["created_at"], float)


def test_list_jobs_returns_inserted_row(scheduler: BatchScheduler) -> None:
    scheduler.enqueue(template_id="t1", project_spec={"a": 1})
    scheduler.enqueue(template_id="t2", project_spec={"b": 2})
    jobs = scheduler.list_jobs(limit=10)
    assert len(jobs) == 2
    assert {j["template_id"] for j in jobs} == {"t1", "t2"}
    for j in jobs:
        # The fixed cursor.description code path should return all SELECT *
        # columns including these.
        for k in ("job_id", "status", "project_spec", "created_at", "result"):
            assert k in j


def test_get_missing_job_returns_none(scheduler: BatchScheduler) -> None:
    assert scheduler.get_job("nonexistent") is None
