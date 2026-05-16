"""Mock music adapter — multi-frequency harmonics for BGM/SFX (REQ-EXT-006)."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Any

SAMPLE_RATE = 24_000


class MockMusicAdapter:
    name = "MockMusicAdapter"

    def __init__(self, *, artefacts_root: Path) -> None:
        self.artefacts_root = artefacts_root

    def render_bgm(
        self,
        *,
        episode_id: str,
        seconds: float,
        mood: str = "tense",
        seed: int = 0,
    ) -> dict[str, Any]:
        out = self.artefacts_root / f"{episode_id}_bgm.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        n = int(SAMPLE_RATE * seconds)
        # mood -> chord
        chord = {
            "tense": (220.0, 277.18, 329.63),
            "warm": (261.63, 329.63, 392.00),
            "epic": (146.83, 220.0, 329.63),
            "calm": (261.63, 311.13, 392.00),
            "neutral": (220.0, 261.63, 329.63),
        }.get(mood, (220.0, 261.63, 329.63))
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            chunks = bytearray()
            two_pi = 2 * math.pi
            for i in range(n):
                t = i / SAMPLE_RATE
                env = 0.10 + 0.05 * math.sin(two_pi * (1.0 / max(1.0, seconds)) * t)
                s = sum(math.sin(two_pi * f * t) for f in chord) / len(chord)
                v = int(env * s * 32760)
                if v > 32767:
                    v = 32767
                if v < -32768:
                    v = -32768
                chunks += struct.pack("<h", v)
            w.writeframes(bytes(chunks))
        return {"bgm_uri": str(out), "duration_s": seconds, "mood": mood}
