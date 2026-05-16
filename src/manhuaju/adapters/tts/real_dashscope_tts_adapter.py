"""Real DashScope CosyVoice TTS adapter (M3).

Uses the DashScope `SpeechSynthesizer` SDK to synthesize a single line from
text + voice profile mapping, writes the result as 24kHz mono WAV to the same
location the mock adapter would, and tracks cost.

Surface mirrors `MockTTSAdapter.synthesise(TTSRequest) -> dict`. On any
provider error we degrade to `mock_fallback` so episode flow never blocks.
"""

from __future__ import annotations

import time
import wave
from pathlib import Path
from typing import Any

from manhuaju.adapters.tts.mock_tts_adapter import SAMPLE_RATE, MockTTSAdapter, TTSRequest
from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s
from manhuaju.core.provider_settings import ProviderSettings

_VOICE_TABLE: dict[tuple[str, str], str] = {
    # (timbre, energy) → DashScope voice id (cosyvoice-v1)
    ("warm", "low"): "longxiaobai",
    ("warm", "medium"): "longxiaochun",
    ("warm", "high"): "longxiaocheng",
    ("bright", "low"): "longxiaobai",
    ("bright", "medium"): "longxiaocheng",
    ("bright", "high"): "longwan",
    ("neutral", "low"): "longxiaochun",
    ("neutral", "medium"): "longxiaochun",
    ("neutral", "high"): "longxiaocheng",
    ("soft", "low"): "longxiaobai",
    ("soft", "medium"): "longxiaobai",
    ("soft", "high"): "longxiaochun",
    ("raspy", "low"): "longxiaocheng",
    ("raspy", "medium"): "longxiaocheng",
    ("raspy", "high"): "longwan",
}


class RealDashScopeTTSAdapter:
    name = "RealDashScopeTTSAdapter"
    provider = "dashscope_cosyvoice"

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        cost: CostTracker,
        config: dict[str, Any] | None = None,
        artefacts_root: Path | None = None,
        mock_fallback: MockTTSAdapter | None = None,
    ) -> None:
        self._settings = settings
        self._cost = cost
        self._cfg = config or {}
        self.artefacts_root = artefacts_root or Path("./live_tts")
        self.artefacts_root.mkdir(parents=True, exist_ok=True)
        self.mock_fallback = mock_fallback
        self._model = self._cfg.get("model", "cosyvoice-v1")
        self._sample_rate = int(self._cfg.get("sample_rate", SAMPLE_RATE))

    def synthesise(self, req: TTSRequest) -> dict[str, Any]:
        if not self._settings.dashscope_key:
            return self._fallback(req)

        voice = _VOICE_TABLE.get((req.timbre, req.energy), "longxiaochun")
        out_path = self.artefacts_root / f"{req.line_id}.wav"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        t0 = now_s()
        audio_bytes: bytes | None = None
        err: str | None = None
        synthesizer = None
        try:
            import dashscope  # type: ignore[import-not-found]
            from dashscope.audio.tts_v2 import SpeechSynthesizer  # type: ignore[import-not-found]

            dashscope.api_key = self._settings.dashscope_key
            synthesizer = SpeechSynthesizer(model=self._model, voice=voice)
            audio_bytes = synthesizer.call(req.text or " ")
        except Exception as e:  # noqa: BLE001 — degrade on any SDK failure
            err = type(e).__name__
        finally:
            # Always close the SDK synthesizer to release the websocket thread,
            # otherwise Python won't exit cleanly at script end.
            if synthesizer is not None:
                try:
                    synthesizer.close()
                except Exception:  # noqa: BLE001
                    pass
        duration = now_s() - t0

        if not audio_bytes:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider="dashscope_cosyvoice",
                    operation="tts.synthesise",
                    model=self._model,
                    duration_s=duration,
                    success=False,
                    error_class=err or "empty_audio",
                )
            )
            return self._fallback(req)

        # CosyVoice returns 22kHz PCM-WAV bytes already. Persist and probe.
        out_path.write_bytes(audio_bytes)
        try:
            with wave.open(str(out_path), "rb") as wf:
                duration_s = wf.getnframes() / float(wf.getframerate() or self._sample_rate)
        except Exception:  # noqa: BLE001
            duration_s = float(req.seconds)

        rmb = self._cost.estimate_tts("dashscope", len(req.text or ""))
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider="dashscope_cosyvoice",
                operation="tts.synthesise",
                model=self._model,
                duration_s=duration,
                rmb=rmb,
                success=True,
                extra={"line_id": req.line_id, "voice": voice},
            )
        )

        # Lip-sync metadata: same scheme as mock so downstream consumers don't change.
        viseme_alphabet = "AEIOUMBP"
        ms_per_visume = 80
        nv = max(1, int(duration_s * 1000 // ms_per_visume))
        visemes = []
        for i in range(nv):
            ch = req.text[i % max(1, len(req.text))] if req.text else "_"
            v = viseme_alphabet[(ord(ch) + i) % len(viseme_alphabet)]
            visemes.append({"t_ms": i * ms_per_visume, "viseme": v})

        return {
            "line_id": req.line_id,
            "wav_uri": str(out_path),
            "duration_s": duration_s,
            "lipsync": visemes,
            "voice_profile": {
                "base_pitch_hz": float(req.base_pitch_hz),
                "timbre": req.timbre,
                "energy": req.energy,
                "provider_voice": voice,
            },
        }

    def _fallback(self, req: TTSRequest) -> dict[str, Any]:
        if self.mock_fallback is None:
            raise RuntimeError("DashScope TTS unavailable and no mock_fallback")
        return self.mock_fallback.synthesise(req)
