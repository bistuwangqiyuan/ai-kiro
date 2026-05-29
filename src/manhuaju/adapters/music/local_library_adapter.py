"""Local BGM Library 适配器 — 国内默认 Shell 5 BGM 方案.

无需任何外部 API，从本地 CC0 曲库按题材/情绪挑选。
内部使用 ffmpeg 将曲目混音/裁切到指定时长 + 加淡入淡出，
保持与 ``RealElevenLabsMusicAdapter`` 完全一致的接口形态。

Library layout (默认 ``assets/bgm/`` 下面，可通过 config.music.library_root 配置):

    assets/bgm/
        ancient/      ← 古风
            *.mp3 / *.wav / *.m4a
        modern/
        sweet_pet/
        suspense/
        xuanhuan/
        ...
        _default/     ← 兜底（无对应题材时用）

如果对应目录或文件不存在，会生成一段简谐合成的「静音占位」WAV，
不会让 pipeline 中断 —— 视频依然能出片，只是 BGM 为空轨。
"""

from __future__ import annotations

import hashlib
import math
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s


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


class LocalMusicLibraryAdapter:
    """从本地曲库挑曲并用 ffmpeg 裁切到目标时长。"""

    name = "LocalMusicLibraryAdapter"
    provider = "local_library"

    SUPPORTED_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")

    def __init__(
        self,
        library_root: str | Path = "assets/bgm",
        sample_rate: int = 44100,
        channels: int = 2,
        bitrate: str = "192k",
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.library_root = Path(library_root)
        self.sample_rate = sample_rate
        self.channels = channels
        self.bitrate = bitrate
        self.cost = cost_tracker
        self._ffmpeg = shutil.which("ffmpeg")

    # --------------------------------------------------------------
    # public
    # --------------------------------------------------------------

    def render_bgm(
        self,
        *,
        episode_id: str,
        seconds: float,
        mood: str = "tense",
        seed: int = 0,
        genre: str | None = None,
    ) -> dict[str, Any]:
        """Same contract as ``MockMusicAdapter.render_bgm`` for MusicDirectorAgent."""
        mood_to_genre = {
            "tense": "suspense",
            "warm": "sweet_pet",
            "epic": "xuanhuan",
            "calm": "ancient",
            "neutral": "modern",
        }
        pick_genre = genre or mood_to_genre.get(mood, "ancient")
        out_path = Path(f"/tmp/manhuaju_bgm_{episode_id}_{int(seconds)}.mp3")
        result = self.synthesize(
            duration_s=seconds,
            genre=pick_genre,
            out_path=out_path,
            seed=seed,
        )
        return {
            "bgm_uri": result.local_path,
            "duration_s": result.duration_s,
            "mood": mood,
        }

    def synthesize(
        self,
        emotion_arc: list[dict[str, Any]] | None = None,
        duration_s: float = 75.0,
        instrumental: bool = True,
        *,
        genre: str | None = None,
        out_path: str | Path | None = None,
        seed: int | None = None,
    ) -> MusicResult:
        """根据情绪弧/题材挑曲并裁到 ``duration_s``."""
        start = now_s()
        out_path = Path(out_path or f"/tmp/manhuaju_bgm_{int(start * 1000)}.mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 1) 挑曲：按题材，再用情绪+seed 决定挑哪首
        candidate_dir = self._candidate_dir(genre, emotion_arc)
        source = self._pick_track(candidate_dir, emotion_arc=emotion_arc, seed=seed)

        if source is None:
            # 全无曲库 → 生成静音占位 WAV，不中断
            wav_out = out_path.with_suffix(".wav")
            self._render_silence(wav_out, duration_s)
            self._book_cost(duration_s)
            return MusicResult(
                local_path=str(wav_out),
                duration_s=duration_s,
                sample_rate=self.sample_rate,
                channels=1,
                bitrate="silence",
                provider=self.provider,
                model="silence-fallback",
                success=True,
                error="no library tracks found; silent bgm placeholder",
            )

        # 2) 裁切到目标时长：用 ffmpeg apad / atrim + 淡入淡出
        ok = self._render_with_ffmpeg(source, out_path, duration_s)
        if not ok:
            # ffmpeg 不可用 → 直接复制原文件（让上层至少有可挂载的音轨）
            shutil.copy2(source, out_path)

        self._book_cost(duration_s)
        return MusicResult(
            local_path=str(out_path),
            duration_s=duration_s,
            sample_rate=self.sample_rate,
            channels=self.channels,
            bitrate=self.bitrate,
            provider=self.provider,
            model=f"library:{candidate_dir.name}/{source.name}",
            success=True,
        )

    # --------------------------------------------------------------
    # internals
    # --------------------------------------------------------------

    def _candidate_dir(
        self,
        genre: str | None,
        emotion_arc: list[dict[str, Any]] | None,
    ) -> Path:
        candidates: list[Path] = []
        if genre:
            candidates.append(self.library_root / genre)
        if emotion_arc:
            # 取出现频次最高的情绪做二级匹配
            counts: dict[str, int] = {}
            for e in emotion_arc:
                k = str(e.get("emotion") or e.get("name") or "").lower()
                if k:
                    counts[k] = counts.get(k, 0) + 1
            top = max(counts.items(), key=lambda x: x[1])[0] if counts else None
            if top:
                candidates.append(self.library_root / top)
        candidates.append(self.library_root / "_default")
        candidates.append(self.library_root)
        for c in candidates:
            if c.exists() and any(self._iter_tracks(c)):
                return c
        # 全空：返回最后一个（可能也是空），上层会触发 silence fallback
        return candidates[-1]

    def _iter_tracks(self, root: Path):
        if not root.exists():
            return
        for p in sorted(root.iterdir()):
            if p.is_file() and p.suffix.lower() in self.SUPPORTED_EXTS:
                yield p

    def _pick_track(
        self,
        directory: Path,
        *,
        emotion_arc: list[dict[str, Any]] | None,
        seed: int | None,
    ) -> Path | None:
        tracks = list(self._iter_tracks(directory))
        if not tracks:
            return None
        key = f"{seed or 0}-{len(emotion_arc or [])}"
        idx = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % len(tracks)
        return tracks[idx]

    def _render_with_ffmpeg(self, src: Path, dst: Path, duration_s: float) -> bool:
        if not self._ffmpeg or not src.exists():
            return False
        # apad 让短曲循环补齐；atrim 裁切；afade 入 1s / 出 2s
        cmd = [
            self._ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-stream_loop",
            "-1",
            "-i",
            str(src),
            "-t",
            f"{duration_s:.2f}",
            "-af",
            f"afade=t=in:st=0:d=1,afade=t=out:st={max(0.0, duration_s - 2.0):.2f}:d=2",
            "-c:a",
            "libmp3lame",
            "-b:a",
            self.bitrate,
            "-ar",
            str(self.sample_rate),
            "-ac",
            str(self.channels),
            str(dst),
        ]
        try:
            r = subprocess.run(cmd, check=False, timeout=120, capture_output=True)
            return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0
        except (subprocess.SubprocessError, OSError):
            return False

    def _render_silence(self, dst: Path, duration_s: float) -> None:
        n_frames = int(self.sample_rate * max(0.5, duration_s))
        with wave.open(str(dst), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            # 极低能量正弦波 (-50dB) 用作占位；几乎听不见但不是绝对 0
            amp = int(0.0032 * 32767)  # ≈ -50dBFS
            for i in range(n_frames):
                v = int(amp * math.sin(2 * math.pi * 220.0 * i / self.sample_rate))
                wf.writeframesraw(struct.pack("<h", v))

    def _book_cost(self, duration_s: float) -> None:
        if self.cost is None:
            return
        # 本地曲库零成本，仅记录调用次数
        self.cost.add(
            CostEntry(
                ts=now_s(),
                provider=self.provider,
                kind="music",
                amount_rmb=0.0,
                detail=f"local library {duration_s:.0f}s",
            )
        )
