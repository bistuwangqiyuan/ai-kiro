"""REQ-PILOT-009: One injected 5xx must be recovered without manual fault."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from manhuaju.adapters.render.mock_seedance_adapter import MockSeedanceAdapter
from manhuaju.adapters.render.mock_xiaoyunque_adapter import (
    MockXiaoyunqueAdapter,
    XiaoyunqueAPIError,
)


def test_chaos_5xx_recoverable(tmp_path: Path) -> None:
    seedance = MockSeedanceAdapter(artefacts_root=tmp_path / "ren", frames_root=tmp_path / "fr")
    xy = MockXiaoyunqueAdapter(
        artefacts_root=tmp_path / "ren", frames_root=tmp_path / "fr", seedance_fallback=seedance
    )
    xy.inject_5xx_once("shot_chaos")

    payload = dict(
        idem_key="kchaos",
        shot_id="shot_chaos",
        scene_id="ep01_sc01",
        prompt="chaos test",
        prompt_sha="0" * 64,
        seed=1,
        duration_s=1,
        fps=12,
        resolution="720p",
        characters=[{"char_id": "c1", "outfit_id": "c1_outfit_00"}],
        location_id="loc_x",
        mood="tense",
        key_action="anything",
        style_sha="abc12345",
    )
    with pytest.raises(XiaoyunqueAPIError):
        xy.submit(**payload)
    # second attempt with the same idempotency key succeeds
    task_id = xy.submit(**payload)
    out = xy.poll(task_id)
    assert out["status"] == "succeeded"


def test_chaos_pilot_evaluation_recovered(pilot_artefacts) -> None:
    item = next(it for it in pilot_artefacts.pilot["items"] if it["name"] == "REQ-PILOT-009")
    assert item["pass"] is True
    assert pilot_artefacts.chaos_recovered is True
