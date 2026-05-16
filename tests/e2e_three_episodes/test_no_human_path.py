"""REQ-PILOT-011: 0 banned tokens in (a) static source scan, (b) runtime events."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_static_forbidden_terms_zero() -> None:
    res = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "lint" / "forbidden_terms.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"forbidden_terms FAILED:\n{res.stdout}\n{res.stderr}"


def test_runtime_no_human_path(pilot_artefacts) -> None:
    assert pilot_artefacts.runtime_violations == 0


def test_pilot_011_pass(pilot_artefacts) -> None:
    item = next(it for it in pilot_artefacts.pilot["items"] if it["name"] == "REQ-PILOT-011")
    assert item["pass"] is True
