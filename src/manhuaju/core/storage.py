"""LocalFS storage (M2 replacement for MinIO/S3 — REQ-NFR-REL-003)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LocalFSStorage:
    """Disk-backed key/blob store rooted at `base`. Path semantics use posix
    separators in keys; converted to filesystem on write."""

    def __init__(self, base: Path) -> None:
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        p = self.base / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write_bytes(self, key: str, data: bytes) -> Path:
        p = self.path(key)
        p.write_bytes(data)
        return p

    def write_text(self, key: str, text: str, *, encoding: str = "utf-8") -> Path:
        p = self.path(key)
        p.write_text(text, encoding=encoding)
        return p

    def write_json(self, key: str, obj: Any) -> Path:
        return self.write_text(
            key, json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
        )

    def read_bytes(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def read_text(self, key: str) -> str:
        return self.path(key).read_text(encoding="utf-8")

    def exists(self, key: str) -> bool:
        return (self.base / key).exists()

    def list(self, prefix: str) -> list[Path]:
        root = self.base / prefix
        if not root.exists():
            return []
        return sorted(p for p in root.rglob("*") if p.is_file())
