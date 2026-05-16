"""Deterministic, provider-friendly text-to-video prompt composition.

Structured shot metadata often uses ``|``-separated clauses; several commercial
models reject that form and return ``FAILED``. This module maps structured
fields into a single fluent English prompt with cinematic quality anchors.
"""

from __future__ import annotations


def _cast_phrase(characters: list[dict]) -> str:
    if not characters:
        return ""
    names: list[str] = []
    for c in characters[:2]:
        n = str(c.get("name") or c.get("char_id") or "").strip()
        if not n:
            continue
        base = n.split(" ")[0].split("_")[-1].strip()
        if not base or base.isdigit() or (len(base) >= 6 and base.isalnum() and sum(c.isdigit() for c in base) >= 4):
            continue
        names.append(base)
    if not names:
        return "Young East Asian protagonists in a premium manga drama"
    if len(names) == 1:
        return f"A young East Asian protagonist named {names[0]}"
    return f"Two young East Asian characters, {names[0]} and {names[1]}"


def compose_fluent_video_prompt(
    *,
    prompt: str,
    characters: list[dict],
    location_id: str,
    mood: str,
    key_action: str,
    quality_suffix: str | None = None,
    max_len: int = 1200,
) -> str:
    """Turn structured storyboard fields into one comma-separated T2V prompt."""
    cast_phrase = _cast_phrase(characters)
    action = key_action.strip() or "moves naturally in the scene"
    location = location_id.replace("_", " ").strip() or "a stylised city street"
    mood_word = (mood or "calm").replace("_", " ")
    clauses_raw = (prompt or "").replace("|", ",").strip(" ,;|")

    parts: list[str] = []
    if cast_phrase:
        parts.append(cast_phrase)
    parts.append(action)
    parts.append(f"in {location}")
    parts.append(f"a {mood_word} atmosphere")
    if clauses_raw:
        parts.append(clauses_raw)
    parts.append(
        quality_suffix
        or (
            "cinematic 2D manga drama, broadcast-quality animation, "
            "rich detail, soft volumetric light, painterly color grade, "
            "smooth temporal coherence, masterpiece framing"
        )
    )
    composed = ", ".join(p.strip(" ,;.") for p in parts if p.strip(" ,;."))
    return composed[:max_len]
