"""Project layout helpers."""

from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]


def project_root() -> Path:
    return ROOT_DIR


def config_dir() -> Path:
    return ROOT_DIR / "config"


def runs_dir(base: Path | None = None) -> Path:
    return (base or ROOT_DIR) / "tests" / "e2e_three_episodes" / "output"
