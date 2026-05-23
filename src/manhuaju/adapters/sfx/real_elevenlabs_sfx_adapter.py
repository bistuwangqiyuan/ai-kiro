"""ElevenLabs Sound Generation 适配器 — Shell 5 SFX.

每个 ``audio_cue``（剧本里的拟声/特效提示）单独生成 1 个短音效。
endpoint: https://api.elevenlabs.io/v1/sound-generation
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s
from manhuaju.core.provider_settings import ProviderSettings


@dataclass
class SFXResult:
    cue_id: str
    local_path: str
    duration_s: float
    description: str
    provider: str
    success: bool = True
    error: str | None = None


class RealElevenLabsSFXAdapter:
    name = "RealElevenLabsSFXAdapter"
    provider = "elevenlabs_sfx"

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        cost: CostTracker,
        config: dict[str, Any] | None = None,
        artefacts_root: Path | None = None,
        mock_fallback: Any | None = None,
    ) -> None:
        self._settings = settings
        self._cost = cost
        self._cfg = config or {}
        self.artefacts_root = artefacts_root or Path("./live_sfx")
        self.artefacts_root.mkdir(parents=True, exist_ok=True)
        self._timeout_s = float(self._cfg.get("request_timeout_s", 60))
        self.mock_fallback = mock_fallback

    @property
    def available(self) -> bool:
        return bool(self._settings.elevenlabs_key)

    def synthesize(
        self,
        cue_id: str,
        description: str,
        *,
        duration_s: float = 2.0,
        prompt_influence: float = 0.6,
    ) -> SFXResult:
        if not self.available:
            return self._fallback(cue_id, description, duration_s)

        out_path = self.artefacts_root / f"{cue_id}.mp3"
        body = {
            "text": description[:300],
            "duration_seconds": float(min(max(duration_s, 0.5), 22.0)),
            "prompt_influence": float(prompt_influence),
        }
        t0 = now_s()
        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                r = client.post(
                    "https://api.elevenlabs.io/v1/sound-generation",
                    headers={
                        "xi-api-key": self._settings.elevenlabs_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json=body,
                )
            dur = now_s() - t0
        except (httpx.HTTPError, OSError) as e:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="sfx.synthesize",
                    model="elevenlabs_sfx",
                    duration_s=now_s() - t0,
                    success=False,
                    error_class=type(e).__name__,
                )
            )
            return self._fallback(cue_id, description, duration_s)

        if r.status_code != 200 or not r.content:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="sfx.synthesize",
                    model="elevenlabs_sfx",
                    duration_s=dur,
                    success=False,
                    error_class=f"HTTP {r.status_code}",
                )
            )
            return self._fallback(cue_id, description, duration_s)

        out_path.write_bytes(r.content)
        rmb = self._cost.estimate_sfx("elevenlabs", 1)
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider=self.provider,
                operation="sfx.synthesize",
                model="elevenlabs_sfx",
                duration_s=dur,
                rmb=rmb,
                success=True,
                extra={"cue_id": cue_id, "bytes": len(r.content)},
            )
        )
        return SFXResult(
            cue_id=cue_id,
            local_path=str(out_path),
            duration_s=duration_s,
            description=description,
            provider=self.provider,
        )

    def _fallback(self, cue_id: str, description: str, duration_s: float) -> SFXResult:
        if self.mock_fallback is not None and hasattr(self.mock_fallback, "synthesize"):
            try:
                return self.mock_fallback.synthesize(cue_id, description, duration_s=duration_s)
            except TypeError:
                pass
        return SFXResult(
            cue_id=cue_id,
            local_path="",
            duration_s=duration_s,
            description=description,
            provider="elevenlabs-degraded",
            success=False,
            error="sfx unavailable",
        )
