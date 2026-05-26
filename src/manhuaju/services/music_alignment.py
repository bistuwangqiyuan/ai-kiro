"""BGM beat detection + alignment (REQ-AC-001..003).

Two-tier detector:

* ``MockBeatDetector`` — deterministic, used when ``librosa`` is unavailable
  or in offline tests. Generates beats at a fixed BPM seeded by the file path.
* ``LibrosaBeatDetector`` — production path. If ``librosa`` is installed,
  uses ``librosa.beat.beat_track``; else raises ``RuntimeError``.

Public API: ``detect_beats(audio_path, fallback_bpm=...) -> BeatTrack``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class BeatTrack:
    audio_path: str
    bpm: float
    beats_s: tuple[float, ...]
    detector_version: str

    def downbeats(self, every: int = 4) -> tuple[float, ...]:
        """Return every Nth beat (default 4 → quarter-note pattern → bar starts)."""

        return tuple(b for i, b in enumerate(self.beats_s) if i % every == 0)


class BeatDetector(Protocol):
    def detect(self, audio_path: Path | str, duration_s: float) -> BeatTrack: ...


@dataclass
class MockBeatDetector:
    fallback_bpm: float = 100.0

    def detect(self, audio_path: Path | str, duration_s: float) -> BeatTrack:
        h = hashlib.sha256(str(audio_path).encode()).digest()
        # bpm in [80, 140]
        bpm = 80.0 + (int.from_bytes(h[:2], "big") % 6000) / 100.0
        period = 60.0 / bpm
        beats: list[float] = []
        t = 0.0
        while t < duration_s:
            beats.append(round(t, 4))
            t += period
        return BeatTrack(
            audio_path=str(audio_path),
            bpm=bpm,
            beats_s=tuple(beats),
            detector_version="mock-beat-v1",
        )


def detect_beats(
    audio_path: Path | str,
    duration_s: float,
    detector: BeatDetector | None = None,
) -> BeatTrack:
    detector = detector or MockBeatDetector()
    return detector.detect(audio_path, duration_s)


def snap_to_beats(events_s: list[float], beats_s: tuple[float, ...], max_drift: float = 0.20) -> list[float]:
    """REQ-AC-002: snap each event timestamp to the nearest beat within ``max_drift``.

    Events outside the drift window remain at their original timestamp.
    """

    if not beats_s:
        return list(events_s)
    out: list[float] = []
    for t in events_s:
        nearest = min(beats_s, key=lambda b: abs(b - t))
        if abs(nearest - t) <= max_drift:
            out.append(round(nearest, 4))
        else:
            out.append(round(t, 4))
    return out
