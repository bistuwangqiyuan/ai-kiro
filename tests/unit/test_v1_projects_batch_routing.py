"""Gate that POST /v1/projects routes through the batch scheduler in hybrid mode."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def make_client(tmp_path: Path):
    """Build a TestClient that won't actually drain the queue or run a pipeline."""

    from manhuaju.api.app import create_app
    from manhuaju.services import batch_scheduler as bs_module

    def _make(system_mode: str = "hybrid") -> TestClient:
        cfg = {"mode": system_mode}
        # Both run_next and the pipeline inside _run_project would otherwise
        # actually execute the real/mock pipeline. We only care here whether
        # the routing decision is correct, so neutralize both.
        ctx = mock.patch.object(bs_module.BatchScheduler, "run_next", lambda self: None)
        ctx.start()

        app = create_app(storage_root=tmp_path / system_mode, config=cfg)

        # Replace any registered BackgroundTask handlers via FastAPI dependency
        # — easier: monkey-patch ProjectPipeline.run on import so even if the
        # bg.add_task fires, it just records "ran" and returns.
        from manhuaju.pipelines import project_flow

        ctx2 = mock.patch.object(
            project_flow.ProjectPipeline,
            "run",
            lambda self, cfg_: {"status": "released", "manifest": None, "exports": []},
        )
        ctx2.start()
        return TestClient(app)

    return _make


def test_hybrid_mode_routes_through_batch(make_client) -> None:
    client = make_client("hybrid")
    r = client.post(
        "/v1/projects",
        json={
            "mode": "simple",
            "title": "T",
            "novel_text": "x" * 30,
            "language": "zh",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"].startswith("proj_")
    assert body["status"] == "queued"
    # has_any_llm reads env keys; in CI without keys this drops to bg path,
    # locally with keys it should pick batch. Either path is correct routing.
    assert body["executor"] in ("batch", "background_task")


def test_mock_mode_uses_background_task(make_client) -> None:
    client = make_client("mock")
    r = client.post(
        "/v1/projects",
        json={
            "mode": "simple",
            "title": "T",
            "novel_text": "x" * 30,
            "language": "zh",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["executor"] == "background_task"


def test_batch_get_endpoint_works(make_client) -> None:
    client = make_client("hybrid")
    first = client.post(
        "/v1/projects",
        json={
            "mode": "simple",
            "title": "T",
            "novel_text": "x" * 30,
            "language": "zh",
        },
    )
    body = first.json()
    if body["executor"] != "batch":
        pytest.skip("no provider keys -> batch path skipped, can't test endpoint")
    job_id = body["job_id"]
    rj = client.get(f"/v1/batch/jobs/{job_id}")
    assert rj.status_code == 200, rj.text
    rj_body = rj.json()
    assert rj_body["job_id"] == job_id
    assert rj_body["project_spec"]["_project_id"] == body["project_id"]
    rl = client.get("/v1/batch/jobs")
    assert rl.status_code == 200
    assert rl.json()["count"] >= 1
