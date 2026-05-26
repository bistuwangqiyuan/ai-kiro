"""Shared IO helpers for reading the pricing and benchmark snapshots.

All functions are pure: same path → same result. The on-disk JSON / CSV
files are content-hashed in tests so any drift surfaces immediately.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

PKG_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PKG_ROOT / "data"
PRICING_DIR = DATA_DIR / "pricing"
BENCH_DIR = DATA_DIR / "benchmarks"
COMPUTED_DIR = DATA_DIR / "computed"
FIGURES_DIR = PKG_ROOT / "figures"
REPORTS_DIR = PKG_ROOT / "reports"


@dataclass(frozen=True)
class Snapshot:
    """A versioned, content-addressable input snapshot."""

    name: str
    path: Path
    sha256: str
    payload: Any


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pricing(name: str) -> Snapshot:
    """Load a pricing JSON snapshot by base filename (without extension)."""

    p = PRICING_DIR / f"{name}.json"
    payload = json.loads(p.read_text(encoding="utf-8"))
    return Snapshot(name=name, path=p, sha256=_hash_file(p), payload=payload)


def load_bench(name: str) -> Snapshot:
    """Load a benchmark CSV snapshot by base filename (without extension)."""

    p = BENCH_DIR / f"{name}.csv"
    payload = pd.read_csv(p)
    return Snapshot(name=name, path=p, sha256=_hash_file(p), payload=payload)


def write_computed(name: str, payload: dict[str, Any]) -> Path:
    """Write a computed-output JSON to ``data/computed/{name}.json`` deterministically."""

    COMPUTED_DIR.mkdir(parents=True, exist_ok=True)
    p = COMPUTED_DIR / f"{name}.json"
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    p.write_text(text, encoding="utf-8")
    return p


def load_calibrated_params() -> dict[str, Any]:
    """Read calibrated parameters; return defaults if pilot calibration not yet run."""

    p = COMPUTED_DIR / "calibrated_params.json"
    if not p.exists():
        return {
            "calibration_status": "uncalibrated_defaults",
            "n_pilot_episodes": 0,
            "ci_level": 0.95,
        }
    return json.loads(p.read_text(encoding="utf-8"))
