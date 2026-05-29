"""Unit tests: user-uploaded assets merge into the render reference_map."""

from __future__ import annotations

from pathlib import Path

from manhuaju.core.agent_base import AgentContext
from manhuaju.core.budget_service import BudgetService, make_budget
from manhuaju.core.event_bus import InMemoryEventBus
from manhuaju.core.provenance import ProvenanceStore
from manhuaju.core.storage import LocalFSStorage
from manhuaju.pipelines.project_flow import ProjectFlowConfig, ProjectPipeline


def _pipe(tmp_path: Path) -> ProjectPipeline:
    ctx = AgentContext(
        storage=LocalFSStorage(tmp_path / "fs"),
        bus=InMemoryEventBus(tmp_path / "events.jsonl"),
        budget=BudgetService(make_budget("S")),
        provenance=ProvenanceStore(tmp_path / "prov"),
        config={},
    )
    return ProjectPipeline(ctx, redlines=[])


def _cfg(**kw: object) -> ProjectFlowConfig:
    return ProjectFlowConfig(project_id="p", novel_text="x" * 20, seed=1, **kw)


def test_character_assets_prepended_to_each_character(tmp_path: Path) -> None:
    pipe = _pipe(tmp_path)
    ref_map = {"char_hero": ["auto1", "auto2"], "scene:loc": ["sc1"]}
    cfg = _cfg(character_asset_urls=["https://t/user.png"])
    pipe._merge_user_assets(ref_map, cfg)
    # User url is prepended (priority) and existing auto refs kept.
    assert ref_map["char_hero"][0] == "https://t/user.png"
    assert "auto1" in ref_map["char_hero"]
    # Scene keys are not touched by character assets.
    assert ref_map["scene:loc"] == ["sc1"]


def test_character_assets_without_existing_chars_uses_fallback_key(tmp_path: Path) -> None:
    pipe = _pipe(tmp_path)
    ref_map: dict[str, list[str]] = {"scene:loc": ["sc1"]}
    cfg = _cfg(character_asset_urls=["https://t/user.png"])
    pipe._merge_user_assets(ref_map, cfg)
    assert ref_map["user:character"] == ["https://t/user.png"]


def test_explicit_asset_refs_merge_by_key(tmp_path: Path) -> None:
    pipe = _pipe(tmp_path)
    ref_map = {"scene:loc_palace": ["auto_scene"]}
    cfg = _cfg(asset_ref_urls={"scene:loc_palace": ["https://t/s.png"], "style_user": ["https://t/st.png"]})
    pipe._merge_user_assets(ref_map, cfg)
    assert ref_map["scene:loc_palace"][0] == "https://t/s.png"
    assert "auto_scene" in ref_map["scene:loc_palace"]
    assert ref_map["style_user"] == ["https://t/st.png"]


def test_no_assets_is_noop(tmp_path: Path) -> None:
    pipe = _pipe(tmp_path)
    ref_map = {"char_hero": ["auto1"]}
    pipe._merge_user_assets(ref_map, _cfg())
    assert ref_map == {"char_hero": ["auto1"]}


def test_no_duplicate_when_url_already_present(tmp_path: Path) -> None:
    pipe = _pipe(tmp_path)
    ref_map = {"char_hero": ["https://t/user.png", "auto1"]}
    cfg = _cfg(character_asset_urls=["https://t/user.png"])
    pipe._merge_user_assets(ref_map, cfg)
    assert ref_map["char_hero"].count("https://t/user.png") == 1
