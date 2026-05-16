"""REQ-PILOT-010: 95% of pure-JSON artefacts must be bit-identical across runs."""

from __future__ import annotations


def test_determinism_rate_at_least_95pct(pilot_artefacts) -> None:
    rate = pilot_artefacts.determinism_rate
    assert rate is not None
    assert rate >= 0.95, f"determinism rate {rate}"


def test_pilot_010_pass(pilot_artefacts) -> None:
    item = next(it for it in pilot_artefacts.pilot["items"] if it["name"] == "REQ-PILOT-010")
    assert item["pass"] is True
