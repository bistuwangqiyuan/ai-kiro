"""REQ-PILOT-003: LAION mean ≥ 6.0 / worst ≥ 5.5; REQ-PILOT-004: VBench ≥ 0.85."""

from __future__ import annotations


def test_laion_mean_above_threshold(pilot_artefacts) -> None:
    for ep in pilot_artefacts.manifest["episodes"]:
        assert ep["aesthetic_mean"] >= 6.0, f"{ep['episode_id']} aesthetic_mean {ep['aesthetic_mean']}"


def test_vbench_subject_above_threshold(pilot_artefacts) -> None:
    for ep in pilot_artefacts.manifest["episodes"]:
        assert ep["vbench_mean"] >= 0.85, f"{ep['episode_id']} vbench_mean {ep['vbench_mean']}"


def test_pilot_003_004_pass(pilot_artefacts) -> None:
    items = {it["name"]: it for it in pilot_artefacts.pilot["items"]}
    assert items["REQ-PILOT-003"]["pass"] is True
    assert items["REQ-PILOT-004"]["pass"] is True
