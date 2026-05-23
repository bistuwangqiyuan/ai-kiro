"""Copyright similarity check — docx 七节「合规版权」.

策略：
1. SimHash 64-bit 全文哈希，与本地语料库（``corpus_dir`` 下的 .txt）逐一对比；
2. Hamming distance / 64 → similarity；阈值 ≥ ``similarity_threshold`` 视为命中；
3. 命中 → 可选调用 LLM 二次仲裁；最终输出 ``verdict + matches``。

可选：上传 TOS + 调火山审核 API（VK_RISK 等）做二次审核。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CopyrightMatch:
    source: str           # corpus file path
    similarity: float     # 0..1
    excerpt: str          # first 80 chars of source


@dataclass
class CopyrightVerdict:
    verdict: str          # pass | warn | block
    max_similarity: float
    matches: list[CopyrightMatch] = field(default_factory=list)
    notes: str = ""


class CopyrightChecker:
    def __init__(
        self,
        *,
        corpus_dir: str | Path | None = None,
        similarity_threshold: float = 0.85,
        block_threshold: float = 0.95,
        llm: Any | None = None,
        simhash_bits: int = 64,
    ) -> None:
        self._corpus_dir = Path(corpus_dir) if corpus_dir else None
        self._sim_threshold = float(similarity_threshold)
        self._block_threshold = float(block_threshold)
        self._llm = llm
        self._bits = int(simhash_bits)
        self._corpus: list[tuple[Path, int, str]] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._corpus_dir or not self._corpus_dir.exists():
            return
        for f in self._corpus_dir.rglob("*.txt"):
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if not text.strip():
                continue
            self._corpus.append((f, simhash(text, bits=self._bits), text[:200]))

    def check(self, text: str) -> CopyrightVerdict:
        self._ensure_loaded()
        if not self._corpus:
            return CopyrightVerdict(verdict="pass", max_similarity=0.0)
        h = simhash(text, bits=self._bits)
        matches: list[CopyrightMatch] = []
        max_sim = 0.0
        for src, src_h, excerpt in self._corpus:
            sim = 1.0 - hamming(h, src_h) / float(self._bits)
            if sim > max_sim:
                max_sim = sim
            if sim >= self._sim_threshold:
                matches.append(
                    CopyrightMatch(source=str(src), similarity=sim, excerpt=excerpt[:80])
                )
        matches.sort(key=lambda m: -m.similarity)

        if max_sim >= self._block_threshold:
            verdict = "block"
        elif max_sim >= self._sim_threshold:
            verdict = "warn"
        else:
            verdict = "pass"

        notes = ""
        if verdict != "pass" and self._llm is not None and matches:
            with _silence():
                second = self._llm_arbitration(text, matches[0])
                if second == "block":
                    verdict = "block"
                elif second == "pass":
                    verdict = "pass" if max_sim < self._block_threshold else "warn"
                notes = f"llm-arbitration={second}"

        return CopyrightVerdict(
            verdict=verdict,
            max_similarity=max_sim,
            matches=matches[:5],
            notes=notes,
        )

    def _llm_arbitration(self, text: str, top_match: CopyrightMatch) -> str:
        sys = (
            "你是版权合规仲裁员。判断给定文本是否抄袭/高度相似源文本。"
            "仅返回 JSON：{\"verdict\": \"block|warn|pass\", \"reason\": str}。"
        )
        user = (
            f"待审文本（前 1500 字）：\n{text[:1500]}\n\n"
            f"对照源（最相似 {top_match.similarity:.3f}，节选 80 字）：\n{top_match.excerpt}"
        )
        try:
            r = self._llm.complete(system=sys, user=user, max_tokens=512, json_mode=True, label="copyright")
            parsed = getattr(r, "parsed", None) or {}
            return str(parsed.get("verdict", "warn"))
        except Exception:  # noqa: BLE001
            return "warn"


# ============== SimHash impl ==============

def simhash(text: str, *, bits: int = 64) -> int:
    """Tiny 64-bit SimHash. Tokenises by 2-gram chars (works for both zh & en)."""
    if not text:
        return 0
    tokens = _tokenize(text)
    v = [0] * bits
    for tok, w in tokens:
        h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[: bits // 8], "big")
        for i in range(bits):
            bit = (h >> i) & 1
            v[i] += w if bit else -w
    out = 0
    for i in range(bits):
        if v[i] > 0:
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _tokenize(text: str) -> list[tuple[str, int]]:
    text = re.sub(r"\s+", "", text)
    if not text:
        return []
    # 2-gram char tokens
    tokens: dict[str, int] = {}
    for i in range(len(text) - 1):
        tok = text[i : i + 2]
        tokens[tok] = tokens.get(tok, 0) + 1
    return list(tokens.items())


class _silence:
    def __enter__(self):  # type: ignore[no-untyped-def]
        return self

    def __exit__(self, *a):  # type: ignore[no-untyped-def]
        return False
