"""state_journal.jsonl writer + replayer (REQ-MO-002 / REQ-MO-003)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StateJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")

    def append(self, entry: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
            )

    def replay(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
        return out
