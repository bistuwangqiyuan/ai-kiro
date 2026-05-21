"""REQ↔Task traceability check (REQ-NFR-MAINT-002)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / ".kiro" / "specs" / "ai-manhuaju-autopilot"
REQ_PATHS = [
    SPEC_DIR / "requirements.md",
    SPEC_DIR / "requirements-workflow-v2.md",
]
TASKS_PATH = SPEC_DIR / "tasks.md"

REQ_RE = re.compile(
    r"REQ-(?:[A-Z0-9-]+-\d{3}|MODE-[a-z]+|AGENT-v2-\d{3})"
)


def main() -> int:
    if not TASKS_PATH.exists():
        print("[trace] tasks.md not present; skipping", file=sys.stderr)
        return 0
    req_set: set[str] = set()
    for p in REQ_PATHS:
        if p.exists():
            req_set.update(REQ_RE.findall(p.read_text(encoding="utf-8")))
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
