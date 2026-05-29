"""Unit tests for the digital-asset library (services.asset_library)."""

from __future__ import annotations

from pathlib import Path

from manhuaju.services.asset_library import (
    ASSET_TYPES,
    AssetLibrary,
    asset_to_dict,
    make_asset,
)


def _lib(tmp_path: Path) -> AssetLibrary:
    return AssetLibrary(tmp_path / "assets.sqlite")


def test_add_get_roundtrip(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    a = make_asset(
        asset_type="character",
        name="曹操",
        tos_url="https://tos.example.com/assets/x.png",
        local_path=str(tmp_path / "x.png"),
        content_type="image/png",
        size_bytes=1234,
        owner="test1@139.com",
    )
    lib.add(a)
    got = lib.get(a.asset_id)
    assert got is not None
    assert got.name == "曹操"
    assert got.owner == "test1@139.com"
    assert got.asset_type == "character"
    assert got.bytes == 1234


def test_make_asset_normalizes_unknown_type() -> None:
    a = make_asset(
        asset_type="bogus",
        name="",
        tos_url="u",
        local_path="p",
        content_type="",
        size_bytes=0,
    )
    assert a.asset_type == "character"  # falls back to first-class type
    assert a.asset_type in ASSET_TYPES
    assert a.name  # defaulted, non-empty
    assert a.content_type == "image/png"


def test_list_filters_by_owner_and_type(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    lib.add(make_asset(asset_type="character", name="c1", tos_url="u1", local_path="p1",
                       content_type="image/png", size_bytes=1, owner="alice"))
    lib.add(make_asset(asset_type="scene", name="s1", tos_url="u2", local_path="p2",
                       content_type="image/png", size_bytes=1, owner="alice"))
    lib.add(make_asset(asset_type="character", name="anon", tos_url="u3", local_path="p3",
                       content_type="image/png", size_bytes=1, owner=""))

    assert len(lib.list_assets()) == 3
    assert len(lib.list_assets(asset_type="character")) == 2
    assert len(lib.list_assets(owner="alice")) == 2
    assert len(lib.list_assets(owner="alice", asset_type="scene")) == 1
    assert len(lib.list_assets(owner="")) == 1  # only anonymous


def test_resolve_urls_returns_consumable_urls(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    a = make_asset(asset_type="character", name="c", tos_url="https://t/x.png",
                   local_path="p", content_type="image/png", size_bytes=1)
    lib.add(a)
    assert lib.resolve_urls([a.asset_id]) == ["https://t/x.png"]
    # Unknown ids are skipped, not raised.
    assert lib.resolve_urls(["nope", a.asset_id]) == ["https://t/x.png"]


def test_delete_owner_scoped(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    a = make_asset(asset_type="character", name="c", tos_url="u", local_path="p",
                   content_type="image/png", size_bytes=1, owner="alice")
    lib.add(a)
    # Wrong owner cannot delete.
    assert lib.delete(a.asset_id, owner="bob") is False
    assert lib.get(a.asset_id) is not None
    # Correct owner can.
    assert lib.delete(a.asset_id, owner="alice") is True
    assert lib.get(a.asset_id) is None


def test_asset_to_dict_includes_media_url(tmp_path: Path) -> None:
    a = make_asset(asset_type="character", name="c", tos_url="u", local_path="p",
                   content_type="image/png", size_bytes=1)
    d = asset_to_dict(a)
    assert d["media_url"] == f"/media/assets/{a.asset_id}"
    assert d["asset_type"] == "character"
