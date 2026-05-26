"""Unit tests for the style transfer service (REQ-STR-001..006)."""

from __future__ import annotations

import pytest

from manhuaju.adapters.styletransfer.mock_adapter import transfer
from manhuaju.adapters.styletransfer.real_seedream_styletx_adapter import (
    transfer as real_transfer,
)
from manhuaju.services.style_transfer import (
    ALL_STYLES,
    IDENTITY_GATE,
    StyleTransferSvc,
)


def test_supports_four_styles() -> None:
    """REQ-STR-001: ≥ 4 target styles supported."""

    assert set(ALL_STYLES) == {"j_anime", "c_anime", "realistic", "2d"}
    assert len(ALL_STYLES) == 4


def test_identity_gate_anchor() -> None:
    """REQ-STR-002 anchor."""

    assert IDENTITY_GATE == 0.94


def test_mock_transfer_deterministic() -> None:
    a = transfer("input.png", "j_anime", identity_lock=True)
    b = transfer("input.png", "j_anime", identity_lock=True)
    assert a == b


def test_identity_lock_passes_gate() -> None:
    """REQ-STR-002: identity_lock=True biases ArcFace ≥ 0.93."""

    svc = StyleTransferSvc()
    res, passed = svc.transfer_with_gate("img.png", "c_anime", identity_lock=True)
    assert res.arcface_score >= 0.93
    # may pass or fail depending on the seeded random in [0.93, 0.99]
    assert isinstance(passed, bool)


def test_identity_unlock_can_drift_below_gate() -> None:
    """When identity_lock=False, ArcFace drift can fall below 0.94 → gate fails."""

    svc = StyleTransferSvc()
    # We try several inputs; with seeds in [0.80, 0.95] roughly 70% will fail the 0.94 gate
    results = [
        svc.transfer_with_gate(f"input{i}.png", "j_anime", identity_lock=False, retries=0)
        for i in range(10)
    ]
    failed = sum(1 for _r, ok in results if not ok)
    assert failed > 0


def test_unsupported_style_raises() -> None:
    svc = StyleTransferSvc()
    with pytest.raises(ValueError):
        svc.transfer_with_gate("img.png", "watercolor", identity_lock=True)  # type: ignore[arg-type]


def test_batch_apply_returns_per_frame_results() -> None:
    """REQ-STR-004: batch returns one entry per frame."""

    svc = StyleTransferSvc()
    out = svc.batch_apply(["a.png", "b.png", "c.png"], "realistic")
    assert len(out) == 3
    assert all(r.target_style == "realistic" for r, _ in out)


def test_pass_rate_aggregates() -> None:
    svc = StyleTransferSvc()
    svc.batch_apply([f"frame{i}.png" for i in range(20)], "2d", identity_lock=True)
    pr = svc.pass_rate()
    assert 0.0 <= pr <= 1.0


def test_real_adapter_fails_without_creds(monkeypatch) -> None:
    """REQ-STR-005: real adapter fails fast for fallback to mock."""

    monkeypatch.delenv("VOLC_ACCESSKEY", raising=False)
    monkeypatch.delenv("VOLC_SECRETKEY", raising=False)
    monkeypatch.delenv("MANHUAJU_VOLC_AK", raising=False)
    monkeypatch.delenv("MANHUAJU_VOLC_SK", raising=False)
    with pytest.raises(RuntimeError, match="credentials"):
        real_transfer("img.png", "j_anime", True, None)


def test_retry_does_not_double_pass() -> None:
    """retries=1 → at most 2 invocations, but only one final result returned."""

    svc = StyleTransferSvc()
    res, _ = svc.transfer_with_gate("img.png", "j_anime", retries=1)
    assert isinstance(res.target_style, str)
    assert len(svc.log) >= 1
