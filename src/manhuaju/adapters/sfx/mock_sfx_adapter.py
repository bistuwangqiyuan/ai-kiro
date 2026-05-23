"""Mock SFX adapter — generates 24kHz mono WAV burst for each cue."""

from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MockSFXResult:
    cue_id: str
    local_path: str
    duration_s: float
    description: str
    provider: str = "mock_sfx"
    success: bool = True
    error: str | None = None


class MockSFXAdapter:
    name = "MockSFXAdapter"
    provider = "mock_sfx"

    def __init__(self, *, artefacts_root: Path) -> None:
        self.artefacts_root = artefacts_root
        self.artefacts_root.mkdir(parents=True, exist_ok=True)

    def synthesize(
        self, cue_id: str, description: str, *, duration_s: float = 2.0
    ) -> MockSFXResult:
        path = self.artefacts_root / f"{cue_id}.wav"
        self._render_burst(path, duration_s=duration_s, seed=hash(description) & 0xFFFF)
        return MockSFXResult(
            cue_id=cue_id,
            local_path=str(path),
            duration_s=duration_s,
            description=description,
        )

    def _render_burst(self, path: Path, *, duration_s: float, seed: int) -> None:
        sample_rate = 24000
        n_frames = int(duration_s * sample_rate)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            freq = 220 + (seed % 600)
            for i in range(n_frames):
                t = i / sample_rate
                env = math.exp(-3.0 * t)
                v = int(0.4 * 32767 * env * math.sin(2 * math.pi * freq * t))
                wf.writeframes(struct.pack("<h", max(-32768, min(32767, v))))
