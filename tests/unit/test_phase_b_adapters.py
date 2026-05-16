"""Phase B smoke gate: each Mock Adapter is wired to real artefacts."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from manhuaju.adapters.circuit.breaker import CircuitBreaker
from manhuaju.adapters.db.sqlite_repo import SQLiteRepo
from manhuaju.adapters.embedding.mock_embedding_adapter import MockEmbeddingAdapter
from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.adapters.moderation.mock_moderation_adapter import MockModerationAdapter
from manhuaju.adapters.music.mock_music_adapter import MockMusicAdapter
from manhuaju.adapters.qa.mock_qa_evaluator_adapter import (
    MockQAEvaluatorAdapter,
    ShotInputs,
)
from manhuaju.adapters.render.mock_seedance_adapter import MockSeedanceAdapter
from manhuaju.adapters.render.mock_xiaoyunque_adapter import (
    MockXiaoyunqueAdapter,
    XiaoyunqueAPIError,
)
from manhuaju.adapters.tts.mock_tts_adapter import MockTTSAdapter, TTSRequest


@pytest.fixture
def tmp_render_dirs(tmp_path: Path) -> tuple[Path, Path]:
    artefacts = tmp_path / "renders"
    frames = tmp_path / "frames"
    artefacts.mkdir(parents=True, exist_ok=True)
    frames.mkdir(parents=True, exist_ok=True)
    return artefacts, frames


def test_xiaoyunque_renders_real_mp4(tmp_render_dirs: tuple[Path, Path]) -> None:
    artefacts, frames = tmp_render_dirs
    seedance = MockSeedanceAdapter(artefacts_root=artefacts, frames_root=frames)
    adapter = MockXiaoyunqueAdapter(
        artefacts_root=artefacts, frames_root=frames, seedance_fallback=seedance
    )
    task_id = adapter.submit(
        idem_key="k1",
        shot_id="ep01_sh001",
        scene_id="ep01_sc01",
        prompt="cinematic build",
        prompt_sha="0" * 64,
        seed=42,
        duration_s=2,  # keep tests fast; ffmpeg integration validated
        fps=12,
        resolution="720p",
        characters=[{"char_id": "char_lead_a", "outfit_id": "char_lead_a_outfit_00"}],
        location_id="loc_skyport",
        mood="tense",
        key_action="对峙",
        style_sha="abcd1234efgh5678",
    )
    res = adapter.poll(task_id)
    assert res["status"] == "succeeded"
    assert res["output_uri"]
    p = Path(res["output_uri"])
    assert p.exists()
    assert p.stat().st_size > 1024  # > 1 KB


def test_xiaoyunque_chaos_5xx_then_success(tmp_render_dirs: tuple[Path, Path]) -> None:
    artefacts, frames = tmp_render_dirs
    adapter = MockXiaoyunqueAdapter(artefacts_root=artefacts, frames_root=frames)
    adapter.inject_5xx_once("ep01_sh999")
    with pytest.raises(XiaoyunqueAPIError):
        adapter.submit(
            idem_key="kch",
            shot_id="ep01_sh999",
            scene_id="ep01_sc01",
            prompt="x",
            prompt_sha="0" * 64,
            seed=1,
            duration_s=1,
            fps=12,
            resolution="720p",
            characters=[{"char_id": "char_a", "outfit_id": "char_a_outfit_00"}],
            location_id="loc_x",
            mood="tense",
            key_action="对峙",
            style_sha="abcd1234",
        )
    # retry with same idem -> succeeds
    task_id = adapter.submit(
        idem_key="kch",
        shot_id="ep01_sh999",
        scene_id="ep01_sc01",
        prompt="x",
        prompt_sha="0" * 64,
        seed=1,
        duration_s=1,
        fps=12,
        resolution="720p",
        characters=[{"char_id": "char_a", "outfit_id": "char_a_outfit_00"}],
        location_id="loc_x",
        mood="tense",
        key_action="对峙",
        style_sha="abcd1234",
    )
    res = adapter.poll(task_id)
    assert res["status"] == "succeeded"


def test_tts_writes_valid_wav(tmp_path: Path) -> None:
    adapter = MockTTSAdapter(artefacts_root=tmp_path / "tts")
    res = adapter.synthesise(
        TTSRequest(
            line_id="line_001",
            text="你好世界，这是一段测试。",
            base_pitch_hz=220,
            timbre="warm",
            energy="medium",
            seconds=1.5,
        )
    )
    p = Path(res["wav_uri"])
    assert p.exists()
    with wave.open(str(p), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 24_000
        assert w.getnframes() > 0


def test_music_writes_valid_wav(tmp_path: Path) -> None:
    adapter = MockMusicAdapter(artefacts_root=tmp_path / "music")
    res = adapter.render_bgm(episode_id="ep01", seconds=1.5, mood="tense", seed=1)
    p = Path(res["bgm_uri"])
    assert p.exists()
    with wave.open(str(p), "rb") as w:
        assert w.getnframes() > 0


def test_moderation_blocks_redline_keyword() -> None:
    m = MockModerationAdapter(redlines=["bomb_recipe", "real_celebrity_x"])
    res = m.screen({"prompt": "build a bomb_recipe"})
    assert res["openai_hit"] is True
    assert res["bytedance_hit"] is True


def test_qa_kpi_consistency_above_threshold() -> None:
    qa = MockQAEvaluatorAdapter()
    s = ShotInputs(
        shot_id="ep01_sh001",
        sequence_index=0,
        seed=42,
        characters=[{"char_id": "char_lead_a", "outfit_id": "char_lead_a_outfit_00"}],
        target_seconds=5,
        duration_s=5.0,
        fps=24,
    )
    res = qa.evaluate_shot(s)
    assert res["consistency"]["arcface_mean"] >= 0.92
    assert res["aesthetic"]["laion_mean"] >= 5.0  # mock will sometimes dip; verify structure
    assert res["consistency"]["vbench_subject"] >= 0.82


def test_qa_cross_episode_arcface_outfit_flip_drops() -> None:
    qa = MockQAEvaluatorAdapter()
    same = qa.cross_episode_arcface(
        char_id="char_lead_a",
        outfit_id_a="char_lead_a_outfit_00",
        outfit_id_b="char_lead_a_outfit_00",
    )
    flipped = qa.cross_episode_arcface(
        char_id="char_lead_a",
        outfit_id_a="char_lead_a_outfit_00",
        outfit_id_b="char_lead_a_outfit_BUG",
    )
    assert same >= 0.99  # identical -> ~1
    assert flipped < 0.92  # outfit drift triggers IT loop


def test_llm_blueprint_deterministic() -> None:
    llm = MockLLMAdapter()
    text = "林云雀和陈翊在天港相遇。" * 60
    a = llm.story_blueprint(novel_text=text, project_id="proj_x", seed=1)
    b = llm.story_blueprint(novel_text=text, project_id="proj_x", seed=1)
    assert a == b
    assert len(a["characters"]) >= 3


def test_llm_episode_plan_three() -> None:
    llm = MockLLMAdapter()
    text = "一段足够长的故事文本。" * 200
    bp = llm.story_blueprint(novel_text=text, project_id="proj_y", seed=7)
    plan = llm.episode_plan(blueprint=bp, episode_count=3, seed=7)
    assert len(plan["episodes"]) == 3
    assert plan["plan_sha"]


def test_llm_script_storyboard_chain() -> None:
    llm = MockLLMAdapter()
    text = "段落 一 二 三 四。" * 200
    bp = llm.story_blueprint(novel_text=text, project_id="proj_z", seed=3)
    plan = llm.episode_plan(blueprint=bp, episode_count=3, seed=3)
    ep = plan["episodes"][0]
    script = llm.write_script(episode=ep, characters=bp["characters"], seed=3)
    assert script["scenes"]
    sb = llm.storyboard(script=script, style_sha="abc", seed=3)
    assert sb["shots"]
    for shot in sb["shots"]:
        assert len(shot["characters"]) <= 2


def test_circuit_breaker_opens_then_half_open() -> None:
    cb = CircuitBreaker(name="test", min_samples=4, threshold=0.5, half_open_after_s=0.0)
    for _ in range(2):
        cb.record(False)
    for _ in range(2):
        cb.record(False)
    assert cb.state == "open"
    # half-open after 0s window
    assert cb.allow() is True
    assert cb.state == "half_open"
    cb.record(True)
    assert cb.state == "closed"


def test_sqlite_repo(tmp_path: Path) -> None:
    repo = SQLiteRepo(tmp_path / "kv.sqlite")
    repo.set("a", "1")
    repo.set("b", "2")
    assert repo.get("a") == "1"
    assert repo.all() == {"a": "1", "b": "2"}
    repo.close()


def test_embedding_normalised() -> None:
    e = MockEmbeddingAdapter()
    v = e.embed("hello")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-6
