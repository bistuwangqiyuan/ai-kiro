"""M3 Live e2e — verify the artefacts produced by `scripts/run_live_pilot.py`.

The pipeline itself is run by the script (which prints progress and writes
JSON reports). These tests then read those reports and check the M3
acceptance gates. Tests are skipped if artefacts are missing.

To produce artefacts:
    $env:MANHUAJU_LIVE_E2E = "1"; $env:MANHUAJU_LIVE_MODE = "hybrid"
    python -m scripts.run_live_pilot
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
REPORTS = HERE / "reports"


def _live_enabled() -> bool:
    return os.getenv("MANHUAJU_LIVE_E2E", "0") == "1"


def _maybe_run_live() -> None:
    """If reports are missing and live is opted-in, invoke the runner once."""
    metadata_path = REPORTS / "live_run_metadata.json"
    if metadata_path.exists():
        return
    if not _live_enabled():
        return
    runner = ROOT / "scripts" / "run_live_pilot.py"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(  # noqa: S603 — controlled internal call
        [sys.executable, "-X", "utf8", str(runner)],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        # Even on non-zero, downstream tests will skip / fail with a clearer message.
        pass


@pytest.fixture(scope="session")
def live_metadata() -> dict[str, Any]:
    if not _live_enabled():
        pytest.skip("MANHUAJU_LIVE_E2E != 1 — live e2e is opt-in.")
    _maybe_run_live()
    metadata_path = REPORTS / "live_run_metadata.json"
    if not metadata_path.exists():
        pytest.skip(f"missing live artefacts: {metadata_path}")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def test_live_pipeline_finished(live_metadata: dict[str, Any]) -> None:
    assert live_metadata.get("calls", 0) >= 1, live_metadata
    assert live_metadata["mode"] in {"live", "hybrid", "live-degraded", "hybrid-degraded"}


def test_live_runtime_within_60min(live_metadata: dict[str, Any]) -> None:
    runtime = float(live_metadata["runtime_s"])
    assert runtime <= 60 * 60, f"runtime {runtime:.1f}s exceeds 60-minute cap"


def test_live_cost_within_80rmb(live_metadata: dict[str, Any]) -> None:
    rmb = float(live_metadata["rmb"])
    assert rmb <= 80.0, f"cost ¥{rmb:.4f} exceeds ¥80 cap"


def test_live_final_report_present(live_metadata: dict[str, Any]) -> None:
    assert (REPORTS / "final_report.md").exists()
    assert (REPORTS / "kpi_summary.json").exists()
    assert (REPORTS / "live_cost_summary.json").exists()


def test_live_real_providers_attempted(live_metadata: dict[str, Any]) -> None:
    if str(live_metadata.get("mode", "")).endswith("degraded"):
        pytest.skip("Bundle was degraded — no real providers attempted.")
    providers = live_metadata.get("providers_called", [])
    assert providers, "no live providers attempted"
    assert any(p.startswith(("dashscope", "volcengine")) for p in providers), providers


def test_live_episode_artefact_exists(live_metadata: dict[str, Any]) -> None:
    out_dir = HERE / "output"
    mp4s = list(out_dir.rglob("*.mp4"))
    assert mp4s, f"no MP4 produced under {out_dir}"
