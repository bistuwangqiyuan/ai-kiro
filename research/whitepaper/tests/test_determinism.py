"""Determinism guarantees for the whitepaper.

Running the same model with the same seed twice MUST produce byte-identical
JSON output and identical hashes. This is the contract the spec leans on.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from research.whitepaper import SEED
from research.whitepaper.models import _io


@pytest.fixture(autouse=True)
def _ensure_run_all_executed(tmp_path_factory):
    """Make sure run_all has been executed at least once in this session."""

    if not (_io.COMPUTED_DIR / "cost.json").exists():
        subprocess.run(
            [sys.executable, "-m", "research.whitepaper.scripts.run_all", "--seed", str(SEED)],
            check=True,
        )


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "name",
    [
        "cost",
        "throughput",
        "sla",
        "consistency",
        "seven_dim_qa",
        "repair",
        "scene_reuse",
        "moderation",
        "pareto",
        "calibrated_params",
    ],
)
def test_computed_files_exist(name: str) -> None:
    p = _io.COMPUTED_DIR / f"{name}.json"
    assert p.exists(), f"missing {p}"
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)


def test_run_all_byte_identical_two_runs() -> None:
    """Two consecutive runs with the same seed produce byte-identical JSON."""

    # snapshot current
    files = ["cost", "throughput", "sla", "consistency", "seven_dim_qa", "repair", "scene_reuse", "moderation", "pareto"]
    before = {n: _hash(_io.COMPUTED_DIR / f"{n}.json") for n in files}

    # re-run
    subprocess.run(
        [sys.executable, "-m", "research.whitepaper.scripts.run_all", "--seed", str(SEED), "--skip-figures"],
        check=True,
    )
    after = {n: _hash(_io.COMPUTED_DIR / f"{n}.json") for n in files}

    for n in files:
        assert before[n] == after[n], f"non-deterministic: {n}.json hash drifted"
