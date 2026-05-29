from pathlib import Path

from manhuaju.adapters.music.local_library_adapter import LocalMusicLibraryAdapter


def test_render_bgm_returns_uri(tmp_path) -> None:
    adapter = LocalMusicLibraryAdapter(library_root=tmp_path / "empty_lib")
    bgm = adapter.render_bgm(episode_id="ep01", seconds=2.0, mood="calm", seed=42)
    assert "bgm_uri" in bgm
    assert bgm["duration_s"] == 2.0
    assert Path(bgm["bgm_uri"]).suffix in (".wav", ".mp3")
