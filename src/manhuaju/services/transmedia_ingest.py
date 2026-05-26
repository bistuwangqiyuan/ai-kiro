"""Transmedia ingest (REQ-TM-001..006).

Translates external comic pages or video clips into the project's internal
``StoryBlueprint``-ish structure (a list of ``IngestSegment`` objects), so the
downstream pipeline can treat them like a generated novel. Identity-locking and
copyright provenance are recorded for the moderator (REQ-TM-005).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from manhuaju.services.keyframe_extractor import (
    Keyframe,
    extract_from_comic_pages,
    extract_from_video,
)

SourceKind = Literal["comic", "video"]


@dataclass(frozen=True)
class IngestSegment:
    segment_id: str
    source_kind: SourceKind
    source_path: str
    keyframes: tuple[Keyframe, ...]
    license_kind: Literal["original", "licensed", "fan_made", "unknown"]
    rights_holder: str | None
    fingerprint_sha: str

    @property
    def keyframe_count(self) -> int:
        return len(self.keyframes)


@dataclass
class TransmediaIngestSvc:
    license_required_for_publish: bool = True
    log: list[IngestSegment] = field(default_factory=list)

    def ingest_comic(
        self,
        page_paths: list[Path | str],
        rights_holder: str | None = None,
        license_kind: Literal["original", "licensed", "fan_made", "unknown"] = "fan_made",
        panels_per_page: int = 4,
    ) -> IngestSegment:
        """REQ-TM-001 (comic): comic pages → keyframes + license metadata."""

        if not page_paths:
            raise ValueError("page_paths must not be empty")
        kfs = tuple(extract_from_comic_pages(page_paths, panels_per_page=panels_per_page))
        seg_id = "tm-comic-" + hashlib.sha256(
            "|".join(str(p) for p in page_paths).encode()
        ).hexdigest()[:10]
        fp = self._fingerprint(seg_id, page_paths)
        seg = IngestSegment(
            segment_id=seg_id,
            source_kind="comic",
            source_path=str(page_paths[0]),
            keyframes=kfs,
            license_kind=license_kind,
            rights_holder=rights_holder,
            fingerprint_sha=fp,
        )
        self.log.append(seg)
        return seg

    def ingest_video(
        self,
        video_path: Path | str,
        duration_s: float,
        fps: float = 1.0,
        rights_holder: str | None = None,
        license_kind: Literal["original", "licensed", "fan_made", "unknown"] = "fan_made",
    ) -> IngestSegment:
        """REQ-TM-001 (video): clip → keyframes + license metadata."""

        kfs = tuple(extract_from_video(video_path, duration_s=duration_s, fps=fps))
        seg_id = "tm-vid-" + hashlib.sha256(str(video_path).encode()).hexdigest()[:10]
        fp = self._fingerprint(seg_id, [video_path])
        seg = IngestSegment(
            segment_id=seg_id,
            source_kind="video",
            source_path=str(video_path),
            keyframes=kfs,
            license_kind=license_kind,
            rights_holder=rights_holder,
            fingerprint_sha=fp,
        )
        self.log.append(seg)
        return seg

    def can_publish(self, seg: IngestSegment) -> bool:
        """REQ-TM-005: publish gate — only ``original`` or ``licensed`` content."""

        if not self.license_required_for_publish:
            return True
        return seg.license_kind in ("original", "licensed")

    @staticmethod
    def _fingerprint(seg_id: str, sources: list[Path | str]) -> str:
        h = hashlib.sha256()
        h.update(seg_id.encode())
        for s in sources:
            h.update(str(s).encode())
        return h.hexdigest()
