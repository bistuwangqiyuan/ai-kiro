"""Runtime emotion library service (REQ-EMO-001..007).

Loads ``config/emotion-library.yaml``, exposes resolution helpers, and runs
the ArcFace identity-preservation gate on emotion variants.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from manhuaju.utils.paths import config_dir

#: Anchored to whitepaper consistency.json.lead_refresh_5.window5_mean_lower_ci.
ARCFACE_MIN_DEFAULT = 0.94


@dataclass(frozen=True)
class EmotionEntry:
    tag: str
    zh: str
    aliases: tuple[str, ...]
    face_prompt_zh: str
    face_prompt_en: str
    body_prompt_zh: str
    camera_hint: str
    color_overlay: str
    music_cue: str

    def to_prompt_segment(self, lang: str = "zh") -> str:
        face = self.face_prompt_zh if lang == "zh" else self.face_prompt_en
        if lang == "zh":
            return f"[情绪:{self.zh}] {face}; {self.body_prompt_zh}; 镜头:{self.camera_hint}"
        return f"[EMOTION:{self.tag}] {face}; camera={self.camera_hint}"


@dataclass(frozen=True)
class EmotionVariant:
    char_id: str
    emotion_tag: str
    sha: str
    arcface_score: float
    ref_paths: tuple[str, ...] = ()
    promoted: bool = False

    def passes_gate(self, threshold: float = ARCFACE_MIN_DEFAULT) -> bool:
        return self.arcface_score >= threshold


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@dataclass
class EmotionLibrarySvc:
    """Per-character emotion catalogue.

    The library stores entries from the YAML config, plus any custom
    emotions added at runtime, plus the per-character variant evaluations
    keyed by ``(char_id, emotion_tag)``.
    """

    catalogue: dict[str, EmotionEntry] = field(default_factory=dict)
    variants: dict[tuple[str, str], EmotionVariant] = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: Path | None = None) -> EmotionLibrarySvc:
        path = config_path or (config_dir() / "emotion-library.yaml")
        data = _load_yaml(path)
        cat: dict[str, EmotionEntry] = {}
        for tag, payload in (data.get("emotions") or {}).items():
            cat[tag] = EmotionEntry(
                tag=tag,
                zh=str(payload.get("zh", tag)),
                aliases=tuple(payload.get("aliases", [])),
                face_prompt_zh=str(payload.get("face_prompt_zh", "")),
                face_prompt_en=str(payload.get("face_prompt_en", "")),
                body_prompt_zh=str(payload.get("body_prompt_zh", "")),
                camera_hint=str(payload.get("camera_hint", "")),
                color_overlay=str(payload.get("color_overlay", "")),
                music_cue=str(payload.get("music_cue", "")),
            )
        return cls(catalogue=cat)

    def all_tags(self) -> list[str]:
        return list(self.catalogue.keys())

    def resolve_tag(self, query: str) -> str:
        """Map zh/alias/eng names to a canonical English tag.

        Raises ``KeyError`` if no match.
        """

        q = query.strip().lower()
        for tag, entry in self.catalogue.items():
            if tag.lower() == q or entry.zh.lower() == q:
                return tag
            if q in (a.lower() for a in entry.aliases):
                return tag
        raise KeyError(f"unknown emotion: {query!r}")

    def get(self, tag: str) -> EmotionEntry:
        return self.catalogue[tag]

    def has_at_least_seven_for(self, char_id: str) -> bool:
        """REQ-EMO-001: ≥ 7 base emotions present per locked character."""

        promoted = [v for (cid, _), v in self.variants.items() if cid == char_id and v.promoted]
        return len(promoted) >= 7

    def add_variant(
        self,
        char_id: str,
        emotion_tag: str,
        ref_paths: tuple[str, ...],
        arcface_score: float,
        threshold: float = ARCFACE_MIN_DEFAULT,
    ) -> EmotionVariant:
        """REQ-EMO-002 / -004: persist a variant only if it passes the ArcFace gate."""

        if emotion_tag not in self.catalogue:
            raise KeyError(f"unknown emotion tag: {emotion_tag!r}")
        sha = hashlib.sha256(
            f"{char_id}|{emotion_tag}|{','.join(ref_paths)}|{arcface_score:.4f}".encode()
        ).hexdigest()[:16]
        variant = EmotionVariant(
            char_id=char_id,
            emotion_tag=emotion_tag,
            sha=sha,
            arcface_score=arcface_score,
            ref_paths=ref_paths,
            promoted=arcface_score >= threshold,
        )
        if variant.promoted:
            self.variants[(char_id, emotion_tag)] = variant
        return variant

    def add_custom_emotion(
        self,
        tag: str,
        zh: str,
        face_prompt_zh: str,
        camera_hint: str = "中景",
        color_overlay: str = "neutral",
        music_cue: str = "neutral",
    ) -> EmotionEntry:
        """REQ-EMO-004: extend the catalogue at runtime."""

        if tag in self.catalogue:
            raise ValueError(f"emotion tag already exists: {tag!r}")
        e = EmotionEntry(
            tag=tag,
            zh=zh,
            aliases=(),
            face_prompt_zh=face_prompt_zh,
            face_prompt_en="",
            body_prompt_zh="",
            camera_hint=camera_hint,
            color_overlay=color_overlay,
            music_cue=music_cue,
        )
        self.catalogue[tag] = e
        return e

    def fallback_calm(self) -> EmotionEntry:
        """REQ-EMO-007: degrade-to-calm baseline when generation keeps failing.

        Resolves to ``thoughtful`` if a ``calm`` tag is absent.
        """

        for fallback in ("calm", "thoughtful"):
            if fallback in self.catalogue:
                return self.catalogue[fallback]
        # Last resort — pick the first catalogue entry deterministically.
        return next(iter(self.catalogue.values()))
