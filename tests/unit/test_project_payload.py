"""Tests for browser → API project payload resolution."""

from __future__ import annotations

import pytest

from manhuaju.api.mode_router import ModeRouter
from manhuaju.api.project_payload import resolve_project_create


@pytest.fixture(scope="module")
def router() -> ModeRouter:
    return ModeRouter.load()


def test_simple_mode_payload(router: ModeRouter) -> None:
    raw = {
        "mode": "simple",
        "title": "测试剧",
        "novel_text": "她重生回到那年春天，竹林深处，剑光寒凛。",
        "language": "zh",
    }
    out = resolve_project_create(raw, router=router)
    # Simple-mode defaults are now "1 shortest episode" so anonymous users
    # and the deploy-loop smoke gate can finish a real render inside the
    # 30 min FaaS request budget.
    assert out["episode_count"] == 1
    assert out["episode_duration_s"] == 30
    assert out["genre"] == "modern"
    assert out["template_id"] == "cdrama_classic"
    assert len(out["novel_text"]) >= 10


def test_pro_mode_distribution_platforms(router: ModeRouter) -> None:
    raw = {
        "mode": "pro",
        "novel_text": "现代都市爱情故事，足够长的正文用于通过校验。",
        "distribution_platforms": ["douyin", "bilibili"],
        "genre": "modern",
        "episode_count": 1,
    }
    out = resolve_project_create(raw, router=router)
    assert out["platforms"] == ["douyin", "bilibili"]
    assert out["episode_count"] == 1
