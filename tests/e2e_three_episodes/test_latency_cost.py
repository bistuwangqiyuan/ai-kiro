"""REQ-PILOT-007: per-episode wall-clock ≤ 5 min in mock; cost = 0."""

from __future__ import annotations


def test_per_episode_runtime_under_5min(pilot_artefacts) -> None:
    assert pilot_artefacts.runtime_seconds_per_ep <= 5 * 60, (
        f"per-ep runtime {pilot_artefacts.runtime_seconds_per_ep:.1f}s exceeds 5 min"
    )


def test_pilot_cost_zero_in_mock(pilot_artefacts) -> None:
    item = next(it for it in pilot_artefacts.pilot["items"] if it["name"] == "REQ-PILOT-007")
    assert item["pass"] is True
