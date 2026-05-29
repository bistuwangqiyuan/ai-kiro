"""Unit tests: project payload carries user asset ids through mode routing."""

from __future__ import annotations

from manhuaju.api.project_payload import resolve_project_create


def test_character_asset_ids_passthrough_pro_mode() -> None:
    out = resolve_project_create(
        {
            "mode": "pro",
            "novel_text": "荀彧劝曹操奉天子以令诸侯，曹操采纳其策。",
            "character_asset_ids": ["asset_a", "asset_b"],
        }
    )
    assert out["character_asset_ids"] == ["asset_a", "asset_b"]


def test_character_asset_ids_accepts_comma_string() -> None:
    out = resolve_project_create(
        {
            "novel_text": "一段足够长的小说正文用于测试透传逻辑。",
            "character_asset_ids": "asset_a, asset_b , ",
        }
    )
    assert out["character_asset_ids"] == ["asset_a", "asset_b"]


def test_asset_refs_normalized() -> None:
    out = resolve_project_create(
        {
            "novel_text": "一段足够长的小说正文用于测试透传逻辑。",
            "asset_refs": {"scene:loc_palace": ["s1", "s2"], "style_user": "st1, st2", "empty": []},
        }
    )
    assert out["asset_refs"]["scene:loc_palace"] == ["s1", "s2"]
    assert out["asset_refs"]["style_user"] == ["st1", "st2"]
    assert "empty" not in out["asset_refs"]


def test_defaults_empty_when_absent() -> None:
    out = resolve_project_create({"novel_text": "一段足够长的小说正文用于测试透传逻辑。"})
    assert out["character_asset_ids"] == []
    assert out["asset_refs"] == {}
