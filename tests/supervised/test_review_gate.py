"""Supervised mode tests (REQ-MODE-supervised)."""

from __future__ import annotations

from manhuaju.core.review_gate import ReviewGate


def test_autopilot_never_blocks() -> None:
    gate = ReviewGate(mode="autopilot")
    assert gate.is_release_allowed("proj", "ep01") is True


def test_partial_rerender_action() -> None:
    gate = ReviewGate(mode="supervised")
    out = gate.apply("proj", "ep01", "partial_rerender", note="fix shot 3")
    assert out["decision"] == "partial_rerender"
