"""REQ-PILOT-001 + REQ-PILOT-008.

Asserts: 3 episodes produced; each MP4 exists & non-trivial size;
final_report.md generated.
"""

from __future__ import annotations

from pathlib import Path


def test_three_episodes_produced(pilot_artefacts) -> None:
    eps = pilot_artefacts.manifest["episodes"]
    assert len(eps) >= 3
    for ep in eps:
        p = Path(ep["final_mp4"])
        assert p.exists(), f"missing episode mp4 {p}"
        assert p.stat().st_size > 4 * 1024


def test_final_report_md_exists(pilot_artefacts) -> None:
    p = pilot_artefacts.reports_dir / "final_report.md"
    assert p.exists(), f"final_report.md missing at {p}"
    body = p.read_text(encoding="utf-8")
    assert "Pilot 验收报告" in body
    assert "REQ-PILOT-001" in body
    assert "REQ-PILOT-012" in body


def test_pilot_001_pass(pilot_artefacts) -> None:
    item = next(it for it in pilot_artefacts.pilot["items"] if it["name"] == "REQ-PILOT-001")
    assert item["pass"] is True


def test_pilot_008_pass(pilot_artefacts) -> None:
    item = next(it for it in pilot_artefacts.pilot["items"] if it["name"] == "REQ-PILOT-008")
    assert item["pass"] is True
