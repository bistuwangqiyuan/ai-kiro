"""API smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from manhuaju.api.app import create_app


def test_api_health() -> None:
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
