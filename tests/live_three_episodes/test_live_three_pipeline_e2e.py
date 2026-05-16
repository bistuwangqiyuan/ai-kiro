"""M3 Live three-episode e2e — artefacts from ``scripts.run_live_pilot`` with
``MANHUAJU_LIVE_SUITE=three``.

Run:
    $env:MANHUAJU_LIVE_E2E = "1"
    $env:MANHUAJU_LIVE_SUITE = "three"
    $env:MANHUAJU_LIVE_MODE = "hybrid"
    $env:PYTHONPATH = "src"
    python -m scripts.run_live_pilot
    pytest tests/live_three_episodes -v
"""

from __future__ import annotations

import json
import os
import shutil
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
    metadata_path = REPORTS / "live_run_metadata.json"
    if metadata_path.exists():
        return
    if not _live_enabled():
        return
    runner = ROOT / "scripts" / "run_live_pilot.py"
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONIOENCODING": "utf-8",
        "MANHUAJU_LIVE_SUITE": "three",
    }
    subprocess.run(
        [sys.executable, "-X", "utf8", str(runner)],
        cwd=str(ROOT),
        env=env,
        check=False,
    )


@pytest.fixture(scope="session")
def live_meta() -> dict[str, Any]:
    if not _live_enabled():
        pytest.skip("MANHUAJU_LIVE_E2E != 1")
    _maybe_run_live()
    p = REPORTS / "live_run_metadata.json"
    if not p.exists():
        pytest.skip(f"missing {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def test_three_ep_metadata(live_meta: dict[str, Any]) -> None:
    assert live_meta.get("episode_count_expected") == 3
    assert live_meta.get("episode_count_actual") == 3
    assert live_meta.get("all_pass") is True


def test_final_mp4s_exist_and_nonempty(live_meta: dict[str, Any]) -> None:
    out = HERE / "output" / "episodes"
    for n in (1, 2, 3):
        mp4 = out / f"ep0{n}.mp4"
        assert mp4.exists(), mp4
        assert mp4.stat().st_size > 50_000, f"{mp4} too small — likely mock / failed render"


def test_each_episode_video_under_60s(live_meta: dict[str, Any]) -> None:
    """Final deliverable duration must stay strictly below 60s per episode."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        pytest.skip("ffprobe not on PATH — install ffmpeg for duration assertions")
    out = HERE / "output" / "episodes"
    for n in (1, 2, 3):
        mp4 = out / f"ep0{n}.mp4"
        r = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(mp4),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
        dur = float((r.stdout or "0").strip())
        assert dur < 60.0, f"{mp4.name} duration {dur:.2f}s >= 60s cap"


def test_kpi_summary_all_pass(live_meta: dict[str, Any]) -> None:
    kpi = json.loads((REPORTS / "kpi_summary.json").read_text(encoding="utf-8"))
    assert kpi["pilot"]["all_pass"] is True


def test_real_video_provider_used(live_meta: dict[str, Any]) -> None:
    if str(live_meta.get("mode", "")).endswith("degraded"):
        pytest.skip("degraded bundle")
    prov = live_meta.get("providers_called", [])
    assert any(p.startswith(("dashscope", "volcengine")) for p in prov), prov
