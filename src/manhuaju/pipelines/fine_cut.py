"""Fine cut — subtitles, loudnorm, transitions (REQ-WF-006 step 6)."""

from __future__ import annotations

from pathlib import Path

from manhuaju.pipelines.postprod import burn_subtitle, mux_video_audio, normalise_loudness


def fine_cut_episode(
    *,
    rough_mp4: Path,
    bgm_wav: Path | None,
    out_dir: Path,
    episode_id: str,
    captions: list[str] | None = None,
    fallback_caption: str = "",
) -> Path:
    """Apply per-line or fallback caption burn + final loudness pass."""
    out_dir.mkdir(parents=True, exist_ok=True)
    captioned = rough_mp4
    caption_text = fallback_caption
    if captions:
        caption_text = " · ".join(c for c in captions if c)[:120]
    if caption_text:
        cap_path = out_dir / f"{episode_id}_caption.mp4"
        burn_subtitle(rough_mp4, caption_text, cap_path)
        captioned = cap_path
    if bgm_wav and Path(bgm_wav).exists():
        normed = out_dir / f"{episode_id}_bgm_norm.wav"
        normalise_loudness(bgm_wav, normed)
        final = out_dir / f"{episode_id}.mp4"
        mux_video_audio(captioned, normed, final)
        return final
    final = out_dir / f"{episode_id}.mp4"
    if final != captioned:
        captioned.replace(final)
    return final
