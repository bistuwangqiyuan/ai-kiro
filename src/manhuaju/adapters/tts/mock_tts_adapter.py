"""Mock TTS adapter — sine + ADSR envelope, real 16-bit/24kHz mono WAV.

Drives REQ-EXT-005 (voice profile pinning) and REQ-MD-006 (lip-sync data).
"""

from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAMPLE_RATE = 24_000


def _adsr(n: int, sr: int = SAMPLE_RATE) -> list[float]:
    """attack=10%, decay=10%, sustain=70% @ 0.7, release=10%."""
    a = int(n * 0.10)
    d = int(n * 0.10)
    r = int(n * 0.10)
    s = n - a - d - r
    env: list[float] = []
    for i in range(a):
        env.append(i / max(1, a))
    for i in range(d):
        env.append(1.0 - 0.3 * (i / max(1, d)))
    for _ in range(s):
        env.append(0.7)
    for i in range(r):
        env.append(0.7 * (1.0 - i / max(1, r)))
    while len(env) < n:
        env.append(0.0)
    return env[:n]


@dataclass
class TTSRequest:
    line_id: str
    text: str
    base_pitch_hz: float = 220.0
    timbre: str = "neutral"
    energy: str = "medium"
    seconds: float = 2.0
    out_path: Path | None = None


class MockTTSAdapter:
    name = "MockTTSAdapter"

    def __init__(self, *, artefacts_root: Path) -> None:
        self.artefacts_root = artefacts_root

    def synthesise(self, req: TTSRequest) -> dict[str, Any]:
        n = max(int(SAMPLE_RATE * req.seconds), SAMPLE_RATE // 4)
        # Energy modulates amplitude; timbre modulates harmonic mix.
        amp = {"low": 0.20, "medium": 0.40, "high": 0.65}.get(req.energy, 0.40)
        timbre_mix = {
            "warm": (1.0, 0.5, 0.2),
            "bright": (1.0, 0.2, 0.6),
            "soft": (1.0, 0.1, 0.0),
            "raspy": (1.0, 0.3, 0.45),
            "neutral": (1.0, 0.3, 0.3),
        }.get(req.timbre, (1.0, 0.3, 0.3))
        env = _adsr(n)
        f0 = max(60.0, float(req.base_pitch_hz))
        out = self.artefacts_root / f"{req.line_id}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)

        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            chunks = bytearray()
            two_pi = 2 * math.pi
            for i in range(n):
                t = i / SAMPLE_RATE
                # Sentence intonation: gentle pitch contour
                f = f0 * (1.0 + 0.05 * math.sin(two_pi * 0.5 * t))
                s = (
                    timbre_mix[0] * math.sin(two_pi * f * t)
                    + timbre_mix[1] * math.sin(two_pi * 2 * f * t)
                    + timbre_mix[2] * math.sin(two_pi * 3 * f * t)
                )
                v = int(amp * env[i] * s * 32760)
                if v > 32767:
                    v = 32767
                if v < -32768:
                    v = -32768
                chunks += struct.pack("<h", v)
            w.writeframes(bytes(chunks))

        # lip-sync metadata: viseme per 80 ms window (~12 fps). Determined by
        # text length + index hash. Used for REQ-MD-006 + Pilot syncnet.
        viseme_alphabet = "AEIOUMBP"
        ms_per_visume = 80
        nv = max(1, int(req.seconds * 1000 // ms_per_visume))
        visemes = []
        for i in range(nv):
            ch = req.text[i % max(1, len(req.text))] if req.text else "_"
            v = viseme_alphabet[(ord(ch) + i) % len(viseme_alphabet)]
            visemes.append({"t_ms": i * ms_per_visume, "viseme": v})
        return {
            "line_id": req.line_id,
            "wav_uri": str(out),
            "duration_s": req.seconds,
            "lipsync": visemes,
            "voice_profile": {
                "base_pitch_hz": f0,
                "timbre": req.timbre,
                "energy": req.energy,
            },
        }
