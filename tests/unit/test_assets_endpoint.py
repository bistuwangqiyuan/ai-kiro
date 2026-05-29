"""Unit tests for the /v1/assets upload/list/delete endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from manhuaju.api.app import create_app

# A 1x1 transparent PNG.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f9f0000000049454e44ae426082"
)


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(storage_root=tmp_path))


def test_upload_then_list_then_media_then_delete(client: TestClient) -> None:
    r = client.post(
        "/v1/assets",
        files={"file": ("cao.png", _PNG, "image/png")},
        data={"name": "曹操", "asset_type": "character"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    aid = body["asset_id"]
    assert body["asset_type"] == "character"
    assert body["name"] == "曹操"
    assert body["media_url"] == f"/media/assets/{aid}"

    listed = client.get("/v1/assets?asset_type=character").json()
    assert listed["count"] == 1
    assert listed["assets"][0]["asset_id"] == aid

    media = client.get(f"/media/assets/{aid}")
    assert media.status_code == 200
    assert media.content == _PNG

    assert client.delete(f"/v1/assets/{aid}").status_code == 200
    assert client.get("/v1/assets").json()["count"] == 0


def test_upload_rejects_empty_and_non_image(client: TestClient) -> None:
    r_empty = client.post(
        "/v1/assets",
        files={"file": ("e.png", b"", "image/png")},
        data={"asset_type": "character"},
    )
    assert r_empty.status_code == 400

    r_text = client.post(
        "/v1/assets",
        files={"file": ("note.txt", b"hello world", "text/plain")},
        data={"asset_type": "character"},
    )
    assert r_text.status_code == 415


def test_unknown_asset_type_falls_back_to_character(client: TestClient) -> None:
    r = client.post(
        "/v1/assets",
        files={"file": ("x.png", _PNG, "image/png")},
        data={"asset_type": "weird"},
    )
    assert r.status_code == 200
    assert r.json()["asset_type"] == "character"


def test_delete_missing_returns_404(client: TestClient) -> None:
    assert client.delete("/v1/assets/asset_does_not_exist").status_code == 404
