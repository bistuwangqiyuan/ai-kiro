"""ElevenLabs Music API 适配器 — Shell 5 BGM ★ 版权干净.

接口：``synthesize(emotion_arc, duration_s, instrumental=True) -> MusicResult``
对齐 ``MockMusicAdapter`` 接口形态。

REST endpoint: https://api.elevenlabs.io/v1/music
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
class MusicResult:
    local_path: str
    duration_s: float
    sample_rate: int
    channels: int
    bitrate: str
    provider: str
    model: str
    success: bool = True
    error: str | None = None


class RealElevenLabsMusicAdapter:
    name = "RealElevenLabsMusicAdapter"
    provider = "elevenlabs_music"

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
        self.artefacts_root = artefacts_root or Path("./live_music")
        self.artefacts_root.mkdir(parents=True, exist_ok=True)
        self._timeout_s = float(self._cfg.get("request_timeout_s", 180))
        self.mock_fallback = mock_fallback

    @property
    def available(self) -> bool:
        return bool(self._settings.elevenlabs_key)

    def synthesize(
        self,
        *,
        episode_id: str,
        emotion_arc: str,
        genre: str = "ancient",
        duration_s: int = 75,
        instrumental: bool = True,
        bgm_style: str | None = None,
    ) -> MusicResult:
        if not self.available:
            return self._fallback(episode_id=episode_id, duration_s=duration_s)

        prompt = self._build_prompt(
            emotion_arc=emotion_arc, genre=genre, bgm_style=bgm_style, instrumental=instrumental
        )
        body = {
            "prompt": prompt[:1000],
            "music_length_ms": int(duration_s * 1000),
            "model_id": self._cfg.get("model_id", "eleven_music_v1"),
        }
        if instrumental:
            body["force_instrumental"] = True

        out_path = self.artefacts_root / f"{episode_id}_bgm.mp3"
        t0 = now_s()
        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                r = client.post(
                    "https://api.elevenlabs.io/v1/music",
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
                    operation="music.synthesize",
                    model="eleven_music",
                    duration_s=now_s() - t0,
                    success=False,
                    error_class=type(e).__name__,
                )
            )
            return self._fallback(episode_id=episode_id, duration_s=duration_s)

        if r.status_code != 200 or not r.content:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="music.synthesize",
                    model="eleven_music",
                    duration_s=dur,
                    success=False,
                    error_class=f"HTTP {r.status_code}",
                    extra={"body": r.text[:200] if isinstance(r.text, str) else ""},
                )
            )
            return self._fallback(episode_id=episode_id, duration_s=duration_s)

        out_path.write_bytes(r.content)
        rmb = self._cost.estimate_music("elevenlabs", float(duration_s))
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider=self.provider,
                operation="music.synthesize",
                model="eleven_music",
                duration_s=dur,
                rmb=rmb,
                success=True,
                extra={"episode_id": episode_id, "bytes": len(r.content)},
            )
        )
        return MusicResult(
            local_path=str(out_path),
            duration_s=float(duration_s),
            sample_rate=44100,
            channels=2,
            bitrate="128k",
            provider=self.provider,
            model="eleven_music_v1",
        )

    # parity with MockMusicAdapter
    def synthesise(self, **kwargs: Any) -> MusicResult:
        return self.synthesize(**kwargs)

    def _build_prompt(
        self,
        *,
        emotion_arc: str,
        genre: str,
        bgm_style: str | None,
        instrumental: bool,
    ) -> str:
        parts = [f"漫剧配乐 {emotion_arc}", f"题材 {genre}"]
        if bgm_style:
            parts.append(bgm_style)
        if instrumental:
            parts.append("纯音乐，无人声")
        parts.append("情绪起伏明显，时长精确")
        return "，".join(parts)

    def _fallback(self, *, episode_id: str, duration_s: int) -> MusicResult:
        if self.mock_fallback is None:
            return MusicResult(
                local_path="",
                duration_s=float(duration_s),
                sample_rate=44100,
                channels=2,
                bitrate="0",
                provider="elevenlabs-degraded",
                model="none",
                success=False,
                error="elevenlabs unavailable",
            )
        # Best-effort delegate to mock surface
        for attr in ("synthesize", "synthesise", "generate"):
            fn = getattr(self.mock_fallback, attr, None)
            if callable(fn):
                try:
                    res = fn(
                        episode_id=episode_id,
                        emotion_arc="",
                        duration_s=duration_s,
                        instrumental=True,
                    )
                    local = getattr(res, "local_path", None) or getattr(res, "wav_path", None) or ""
                    return MusicResult(
                        local_path=str(local),
                        duration_s=float(duration_s),
                        sample_rate=getattr(res, "sample_rate", 24000),
                        channels=getattr(res, "channels", 1),
                        bitrate="32k",
                        provider="mock",
                        model="mock-harmonic",
                        success=True,
                    )
                except TypeError:
                    continue
        return MusicResult(
            local_path="", duration_s=float(duration_s), sample_rate=24000,
            channels=1, bitrate="0", provider="mock-unavail", model="none",
            success=False, error="mock fallback signature mismatch",
        )
