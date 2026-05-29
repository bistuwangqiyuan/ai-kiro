from pathlib import Path

from manhuaju.adapters.music.local_library_adapter import LocalMusicLibraryAdapter
from manhuaju.core.cost_tracker import CostTracker


def test_render_bgm_returns_uri(tmp_path) -> None:
    adapter = LocalMusicLibraryAdapter(library_root=tmp_path / "empty_lib")
    bgm = adapter.render_bgm(episode_id="ep01", seconds=2.0, mood="calm", seed=42)
    assert "bgm_uri" in bgm
    assert bgm["duration_s"] == 2.0
    assert Path(bgm["bgm_uri"]).suffix in (".wav", ".mp3")


def test_render_bgm_books_cost_without_crashing(tmp_path) -> None:
    """Regression: _book_cost must work against the real CostTracker API.

    The live pipeline injects a real CostTracker; an outdated ``cost.add`` /
    CostEntry signature previously crashed the whole render at the music step.
    """
    tracker = CostTracker()
    adapter = LocalMusicLibraryAdapter(
        library_root=tmp_path / "empty_lib",
        cost_tracker=tracker,
    )
    bgm = adapter.render_bgm(episode_id="ep02", seconds=1.5, mood="tense", seed=7)
    assert bgm["bgm_uri"]
    # Cost should have been booked through record() without raising.
    assert len(tracker._entries) == 1
    assert tracker._entries[0].operation == "music"
