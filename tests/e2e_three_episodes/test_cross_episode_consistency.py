"""REQ-PILOT-002: cross-episode ArcFace ≥ 0.92 for the lead character."""

from __future__ import annotations


def test_cross_episode_arcface_meets_threshold(pilot_artefacts) -> None:
    matrix = pilot_artefacts.manifest["continuity"]["matrix"]
    assert matrix, "continuity matrix should be non-empty for ≥2 episodes"
    minv = min(
        cell["arcface"]
        for pair in matrix.values()
        for cell in pair.values()
    )
    assert minv >= 0.92, f"cross-episode ArcFace too low: {minv}"


def test_pilot_002_pass(pilot_artefacts) -> None:
    item = next(it for it in pilot_artefacts.pilot["items"] if it["name"] == "REQ-PILOT-002")
    assert item["pass"] is True
