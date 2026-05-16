"""REQ↔Task traceability check (REQ-NFR-MAINT-002).

Scans `.kiro/specs/ai-manhuaju-autopilot/requirements.md` and `tasks.md` for
REQ-IDs and verifies every REQ is referenced by at least one task. Prints a
machine-readable summary; exit non-zero on orphans.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ_PATH = ROOT / ".kiro" / "specs" / "ai-manhuaju-autopilot" / "requirements.md"
TASKS_PATH = ROOT / ".kiro" / "specs" / "ai-manhuaju-autopilot" / "tasks.md"

REQ_RE = re.compile(r"REQ-[A-Z]+-\d{3}")


def main() -> int:
    if not REQ_PATH.exists() or not TASKS_PATH.exists():
        print("[trace] spec not present; skipping", file=sys.stderr)
        return 0
    req_set = set(REQ_RE.findall(REQ_PATH.read_text(encoding="utf-8")))
    task_set = set(REQ_RE.findall(TASKS_PATH.read_text(encoding="utf-8")))
    orphans = sorted(req_set - task_set)
    mapped = len(req_set) - len(orphans)
    print(f"[trace] {len(req_set)} REQs, {mapped} mapped, {len(orphans)} orphan(s)")
    if orphans:
        print("orphans:", ", ".join(orphans))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
