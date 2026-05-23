"""Content safety guard — docx 二节「剧情风控（敏感词、合规改写）」.

三级敏感词：
- ``high``  → 直接 ``block``；
- ``medium`` → 改写 1 次后仍命中 → ``block``；改写成功 → ``rewritten``；
- ``low``  → 仅打 ``warn`` 标签，继续。

LLM 改写策略来自 ``config/sensitive-words.yaml``（``rewrite_strategies`` 字段）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from manhuaju.utils.paths import config_dir


@dataclass
class SafetyHit:
    level: str               # high | medium | low
    category: str
    word: str
    char_index: int = -1
    sentence: str = ""


@dataclass
class SafetyVerdict:
    verdict: str             # pass | rewritten | block
    hits: list[SafetyHit] = field(default_factory=list)
    final_text: str = ""
    rewrite_used: bool = False
    rewrite_attempts: int = 0
    notes: str = ""


class ContentSafetyGuard:
    """Sensitive-word + LLM-aided rewrite + final hard-block."""

    def __init__(
        self,
        *,
        sensitive_words_path: str | Path | None = None,
        llm: Any | None = None,
        max_rewrite: int = 1,
        fail_on_high: bool = True,
        fail_on_medium_after_retry: bool = True,
    ) -> None:
        self._path = Path(sensitive_words_path or (config_dir() / "sensitive-words.yaml"))
        self._llm = llm
        self._max_rewrite = int(max_rewrite)
        self._fail_on_high = fail_on_high
        self._fail_on_medium_after_retry = fail_on_medium_after_retry
        self._lexicon: dict[str, list[tuple[str, str]]] = {"high": [], "medium": [], "low": []}
        self._rewrite_strategies: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        for lvl_key, slot in (data.get("levels") or {}).items():
            cats = (slot or {}).get("categories") or {}
            for cat, words in cats.items():
                for w in words or []:
                    self._lexicon[lvl_key].append((str(w), cat))
        self._rewrite_strategies = (data.get("rewrite_strategies") or {}) or {}

    def scan(self, text: str) -> list[SafetyHit]:
        hits: list[SafetyHit] = []
        for level in ("high", "medium", "low"):
            for word, cat in self._lexicon.get(level, []):
                if not word:
                    continue
                idx = text.find(word)
                while idx >= 0:
                    sent = _extract_sentence(text, idx)
                    hits.append(
                        SafetyHit(
                            level=level, category=cat, word=word,
                            char_index=idx, sentence=sent,
                        )
                    )
                    idx = text.find(word, idx + len(word))
        return hits

    def guard(self, text: str, *, label: str = "content_safety") -> SafetyVerdict:
        hits = self.scan(text)
        if not hits:
            return SafetyVerdict(verdict="pass", hits=[], final_text=text)
        # Hard-block high
        if any(h.level == "high" for h in hits) and self._fail_on_high:
            return SafetyVerdict(
                verdict="block",
                hits=hits,
                final_text=text,
                notes="high-level sensitive word(s) — manual review required",
            )
        # Medium → try LLM rewrite
        if any(h.level == "medium" for h in hits) and self._llm is not None:
            new_text, attempts = self._rewrite(text, hits=hits, label=label)
            new_hits = self.scan(new_text)
            if any(h.level == "medium" for h in new_hits) and self._fail_on_medium_after_retry:
                return SafetyVerdict(
                    verdict="block",
                    hits=new_hits,
                    final_text=new_text,
                    rewrite_used=True,
                    rewrite_attempts=attempts,
                    notes="medium-level sensitive word(s) remained after rewrite",
                )
            if any(h.level == "high" for h in new_hits) and self._fail_on_high:
                return SafetyVerdict(
                    verdict="block",
                    hits=new_hits,
                    final_text=new_text,
                    rewrite_used=True,
                    rewrite_attempts=attempts,
                    notes="rewrite introduced high-level word",
                )
            return SafetyVerdict(
                verdict="rewritten",
                hits=new_hits,
                final_text=new_text,
                rewrite_used=True,
                rewrite_attempts=attempts,
            )
        # Only low-level → warn but pass
        return SafetyVerdict(verdict="pass", hits=hits, final_text=text)

    def _rewrite(self, text: str, *, hits: list[SafetyHit], label: str) -> tuple[str, int]:
        if self._llm is None or not hasattr(self._llm, "complete"):
            return text, 0
        cat_strategies = {
            h.category: self._rewrite_strategies.get(h.category, "")
            for h in hits
            if h.level == "medium"
        }
        strategy_text = "\n".join(f"- {c}: {s}" for c, s in cat_strategies.items() if s)
        sys = (
            "你是内容合规改写助手。请将文本中所有 medium 敏感词替换为委婉、合规表达，"
            "保留剧情含义。返回 JSON: {\"text\": str}。"
            f"\n改写策略：\n{strategy_text}"
        )
        attempts = 0
        current = text
        for _ in range(self._max_rewrite):
            attempts += 1
            try:
                r = self._llm.complete(
                    system=sys,
                    user=current,
                    max_tokens=4096,
                    json_mode=True,
                    label=label,
                )
                parsed = getattr(r, "parsed", None)
                if isinstance(parsed, dict) and parsed.get("text"):
                    current = str(parsed["text"])
                    break
            except Exception:  # noqa: BLE001
                break
        return current, attempts


def _extract_sentence(text: str, idx: int, *, window: int = 40) -> str:
    s = max(0, idx - window)
    e = min(len(text), idx + window)
    # split by zh/en sentence ends
    return re.sub(r"\s+", " ", text[s:e]).strip()
