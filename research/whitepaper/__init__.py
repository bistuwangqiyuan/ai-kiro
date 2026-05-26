"""Quantitative whitepaper for Manhuaju Autopilot v2.0.

All KPI numbers in `need.md` and `.kiro/specs/ai-manhuaju-autopilot/requirements.md`
must be reproducible from the models and scripts in this package, locked by a
single seed (`SEED=20260526`).
"""

from __future__ import annotations

SEED: int = 20260526
"""Global deterministic seed for the whitepaper. Do NOT change without bumping
the report version and re-running every notebook."""
