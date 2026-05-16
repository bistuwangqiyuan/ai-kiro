"""tests/live_one_episode is verification-only — the actual live pipeline run
is performed by `scripts/run_live_pilot.py`. This conftest is intentionally
minimal: it just ensures `src/` is on `sys.path` (already handled by the
top-level conftest) and exposes nothing else.
"""

from __future__ import annotations
