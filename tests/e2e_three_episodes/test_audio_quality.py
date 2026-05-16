"""REQ-PILOT-005: UTMOS ≥ 4.0; REQ-PILOT-006: SyncNet offset ≤ 2 frames."""

from __future__ import annotations


def test_utmos_above_threshold(pilot_artefacts) -> None:
    for ep in pilot_artefacts.manifest["episodes"]:
        assert ep["utmos_mean"] >= 4.0, f"{ep['episode_id']} utmos {ep['utmos_mean']}"


def test_syncnet_offset_within_two_frames(pilot_artefacts) -> None:
    for ep in pilot_artefacts.manifest["episodes"]:
        assert abs(ep["syncnet_offset_max"]) <= 2.0, f"{ep['episode_id']} syncnet {ep['syncnet_offset_max']}"


def test_pilot_005_006_pass(pilot_artefacts) -> None:
    items = {it["name"]: it for it in pilot_artefacts.pilot["items"]}
    assert items["REQ-PILOT-005"]["pass"] is True
    assert items["REQ-PILOT-006"]["pass"] is True
