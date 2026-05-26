"""Inject the resolved emotion tag into a storyboard shot prompt (REQ-EMO-003).

Pure function: given a prompt brief dict (with optional ``dialogue`` and
``character`` fields) and an ``EmotionLibrarySvc``, return a new prompt brief
with the emotion clauses appended.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from manhuaju.services.emotion_library import EmotionLibrarySvc

_HEURISTIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "joy": ("笑", "兴奋", "开心", "雀跃"),
    "anger": ("怒", "气", "怒吼", "拍案"),
    "sadness": ("哭", "泪", "难过", "心碎"),
    "surprise": ("吃惊", "惊", "瞠目", "震惊"),
    "shy": ("羞", "脸红", "低头"),
    "cold": ("冷", "漠然", "无视"),
    "thoughtful": ("沉思", "想", "若有所思"),
    "fear": ("怕", "恐惧", "胆寒"),
    "love": ("爱", "动心", "怦然"),
    "determination": ("决心", "立誓", "下定", "一定"),
}


def auto_resolve_emotion(text: str, lib: EmotionLibrarySvc, default: str = "thoughtful") -> str:
    """Pick the best emotion tag from `text` using simple keyword heuristics."""

    if not text:
        return default
    scores: dict[str, int] = {tag: 0 for tag in lib.all_tags()}
    for tag, kws in _HEURISTIC_KEYWORDS.items():
        if tag not in scores:
            continue
        for kw in kws:
            scores[tag] += len(re.findall(kw, text))
    best = max(scores.items(), key=lambda kv: (kv[1], -lib.all_tags().index(kv[0])))
    return best[0] if best[1] > 0 else default


def inject(
    prompt_brief: dict[str, Any],
    lib: EmotionLibrarySvc,
    *,
    explicit_tag: str | None = None,
    lang: str = "zh",
) -> dict[str, Any]:
    """Return a new prompt brief with an ``[EMOTION:<tag>]`` clause appended.

    Selection priority:
        1. ``explicit_tag`` if given (caller has explicit script-annotated emotion).
        2. Auto-resolve from ``prompt_brief['dialogue']`` text.
    """

    pb = dict(prompt_brief)
    dialogue = pb.get("dialogue", "")
    if explicit_tag:
        try:
            tag = lib.resolve_tag(explicit_tag)
        except KeyError:
            tag = auto_resolve_emotion(dialogue, lib)
    else:
        tag = auto_resolve_emotion(dialogue, lib)
    entry = lib.get(tag)
    clauses = list(pb.get("clauses", []))
    clauses.append(entry.to_prompt_segment(lang=lang))
    pb["clauses"] = clauses
    pb["emotion_tag"] = tag
    pb["emotion_color_overlay"] = entry.color_overlay
    pb["emotion_music_cue"] = entry.music_cue
    return pb


def emotion_token_present(prompt_brief: dict[str, Any]) -> bool:
    """Helper for tests / linters: is at least one [EMOTION:*] / [情绪:*] clause present?"""

    for clause in prompt_brief.get("clauses", []):
        if "[EMOTION:" in clause or "[情绪:" in clause:
            return True
    return False


__all__ = ["auto_resolve_emotion", "inject", "emotion_token_present", "replace"]
