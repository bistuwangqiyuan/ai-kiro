"""ImageUnderstandAdapter — VLM placeholder for reference intent (Phase 2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ImageUnderstandAdapter:
    name = "ImageUnderstandAdapter"

    def analyze(self, image_path: str | Path) -> dict[str, Any]:
        p = Path(image_path)
        return {
            "path": str(p),
            "intent": "character_or_scene_reference",
            "forbidden_elements": [],
            "confidence": 0.85 if p.exists() else 0.0,
        }

    def constraint_clauses(self, image_path: str | Path) -> list[str]:
        meta = self.analyze(image_path)
        return [
            "match reference composition",
            f"avoid: {', '.join(meta['forbidden_elements']) or 'none'}",
        ]
