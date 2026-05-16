"""Real moderation adapter — keyword pre-filter AND LLM judge (M3).

The real system is specced as a two-source AND ensemble (design §8 / REQ-EXT-007).
M3 implementation:

1. Keyword pre-filter against `redlines.yaml`. Cheap, deterministic, offline.
2. LLM judge using a fast cheap model (Groq llama-3.1-8b-instant when available;
   GLM glm-4-flash otherwise) for soft-policy categories (violence, self-harm,
   politically sensitive, sexual minor).

A request is *blocked* iff `(keyword_hit AND llm_hit)` per the dual-AND rule;
soft-block (warn) iff either source hits.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from manhuaju.adapters.moderation.mock_moderation_adapter import MockModerationAdapter
from manhuaju.utils.paths import config_dir

_DEFAULT_REDLINES_PATH = "redlines.yaml"


class RealLLMModerationAdapter:
    name = "RealLLMModerationAdapter"
    provider = "real_llm_moderation"

    def __init__(
        self,
        *,
        llm: Any,
        config: dict[str, Any] | None = None,
        redlines: list[str] | None = None,
        mock_fallback: MockModerationAdapter | None = None,
    ) -> None:
        self._llm = llm
        self._cfg = config or {}
        self._mock_fallback = mock_fallback
        self.redlines = [r.lower() for r in (redlines or _load_redlines())]

    def screen(self, payload: dict[str, Any]) -> dict[str, Any]:
        keyword_hits: list[str] = []
        text_blob_parts: list[str] = []
        for _k, v in payload.items():
            if not isinstance(v, str):
                continue
            text_blob_parts.append(v)
            low = v.lower()
            for rl in self.redlines:
                if rl and rl in low:
                    keyword_hits.append(rl)
                    break
        text_blob = "\n".join(text_blob_parts)[:3000]

        llm_hit, llm_categories = self._llm_judge(text_blob)

        return {
            "openai_hit": bool(keyword_hits),
            "bytedance_hit": llm_hit,
            "hits": keyword_hits,
            "llm_categories": llm_categories,
        }

    def _llm_judge(self, text: str) -> tuple[bool, list[str]]:
        if not text.strip() or self._llm is None:
            return False, []

        prompt = (
            "You are a content safety classifier. Read the text and return JSON:\n"
            '{"violations": [str], "blocked": bool}\n'
            "Where violations is a subset of "
            '["violence_graphic","self_harm","sexual_minor","politically_sensitive",'
            '"hate_speech","illegal_drugs"] and blocked=true iff any severe risk.\n\n'
            f"Text:\n{text}"
        )
        try:
            raw = self._llm.chat(
                messages=[
                    {"role": "system", "content": "Return one JSON object."},
                    {"role": "user", "content": prompt},
                ],
                op="moderation.judge",
                max_tokens=200,
                temperature=0.0,
                json_mode=True,
            )
        except Exception:  # noqa: BLE001
            return False, []

        if not raw:
            return False, []
        text_clean = raw.strip()
        if text_clean.startswith("```"):
            parts = text_clean.split("```", 2)
            if len(parts) >= 2:
                inner = parts[1]
                if inner.lower().startswith("json"):
                    inner = inner[4:]
                text_clean = inner.strip()
        try:
            data = json.loads(text_clean)
        except (json.JSONDecodeError, ValueError):
            first = text_clean.find("{")
            last = text_clean.rfind("}")
            if first >= 0 and last > first:
                try:
                    data = json.loads(text_clean[first : last + 1])
                except (json.JSONDecodeError, ValueError):
                    return False, []
            else:
                return False, []
        if not isinstance(data, dict):
            return False, []
        violations = data.get("violations") or []
        violations = [str(v) for v in violations if isinstance(v, str)]
        blocked = bool(data.get("blocked", False)) or bool(violations)
        return blocked, violations


def _load_redlines() -> list[str]:
    path = config_dir() / _DEFAULT_REDLINES_PATH
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if isinstance(data, dict) and isinstance(data.get("redlines"), list):
        return [str(x) for x in data["redlines"]]
    return []


def _ensure_path() -> Path:
    return config_dir() / _DEFAULT_REDLINES_PATH
