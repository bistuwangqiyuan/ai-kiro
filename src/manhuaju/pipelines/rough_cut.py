"""Rough cut — concat shots + coarse audio alignment (REQ-WF-006 step 5)."""

from __future__ import annotations

from pathlib import Path

from manhuaju.pipelines.postprod import concat_shots, mux_video_audio, normalise_loudness


def rough_cut_episode(
    *,
    shot_mp4s: list[Path],
    bgm_wav: Path | None,
    out_dir: Path,
    episode_id: str,
) -> Path:
    """Concatenate shots and optionally mux coarse BGM without subtitles/effects."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / f"{episode_id}_rough.mp4"
    concat_shots(shot_mp4s, raw)
    if bgm_wav and Path(bgm_wav).exists():
        normed = out_dir / f"{episode_id}_rough_bgm.wav"
        normalise_loudness(bgm_wav, normed)
        muxed = out_dir / f"{episode_id}_rough_mux.mp4"
        mux_video_audio(raw, normed, muxed)
        return muxed
    return raw
