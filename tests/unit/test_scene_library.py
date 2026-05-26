"""Unit tests for the scene library reuse service (REQ-SCN-001..006)."""

from __future__ import annotations

import numpy as np
import pytest

from manhuaju.adapters.embedding.scene_index_adapter import (
    EMBEDDING_DIM,
    MockSceneEmbedder,
    cosine,
)
from manhuaju.services.scene_library import REUSE_THRESHOLD, SceneLibrarySvc


@pytest.fixture
def svc() -> SceneLibrarySvc:
    s = SceneLibrarySvc()
    s.add_scene(
        "tea_house_dawn",
        "A traditional tea house at dawn, lanterns swaying, plum blossoms outside",
        asset_paths=("th_close.png", "th_medium.png", "th_wide.png"),
    )
    s.add_scene(
        "moon_palace",
        "Imperial moon palace at night, jade halls and frozen pond",
        asset_paths=("mp_close.png", "mp_medium.png"),
        available_scales=("close", "medium"),
    )
    return s


def test_threshold_anchor() -> None:
    """REQ-SCN-002: threshold matches whitepaper anchor."""

    assert REUSE_THRESHOLD == 0.85


def test_embedding_dim_constant() -> None:
    e = MockSceneEmbedder().embed("hi")
    assert e.shape == (EMBEDDING_DIM,)
    assert isinstance(e, np.ndarray)


def test_mock_embedder_deterministic() -> None:
    a = MockSceneEmbedder().embed("dawn tea house")
    b = MockSceneEmbedder().embed("dawn tea house")
    assert (a == b).all()


def test_self_similarity_one() -> None:
    e = MockSceneEmbedder().embed("scene-x")
    assert cosine(e, e) == pytest.approx(1.0, abs=1e-6)


def test_reuse_when_identical_description(svc: SceneLibrarySvc) -> None:
    """REQ-SCN-002: identical description → similarity 1 → reuse."""

    d = svc.decide_reuse(
        "A traditional tea house at dawn, lanterns swaying, plum blossoms outside",
        scale="medium",
    )
    assert d.reuse is True
    assert d.matched_scene_id == "tea_house_dawn"
    assert d.similarity == pytest.approx(1.0, abs=1e-6)


def test_no_reuse_when_dissimilar(svc: SceneLibrarySvc) -> None:
    d = svc.decide_reuse("A modern Tokyo subway station with neon billboards", scale="medium")
    assert d.reuse is False
    assert d.similarity < REUSE_THRESHOLD


def test_no_reuse_when_scale_unavailable(svc: SceneLibrarySvc) -> None:
    """REQ-SCN-003: even similar scenes reject when scale isn't in stock."""

    d = svc.decide_reuse(
        "Imperial moon palace at night, jade halls and frozen pond",
        scale="wide",
    )
    assert d.reuse is False, "moon_palace has only close+medium"


def test_reuse_count_increments(svc: SceneLibrarySvc) -> None:
    desc = "A traditional tea house at dawn, lanterns swaying, plum blossoms outside"
    svc.decide_reuse(desc, scale="close")
    svc.decide_reuse(desc, scale="medium")
    rec = svc.scenes["tea_house_dawn"]
    assert rec.reuse_count >= 2


def test_top_k_retrieval(svc: SceneLibrarySvc) -> None:
    """REQ-SCN-001: query returns at most k results sorted descending by similarity.

    The mock embedder is hash-based so semantic similarity is undefined; we verify
    structural correctness only. Production code uses Dashscope text-embedding-v3.
    """

    results = svc.query("any description at all", k=2)
    assert len(results) == 2
    assert results[0][1] >= results[1][1]
    # querying the EXACT description of an entry must surface that entry first
    exact = svc.query("Imperial moon palace at night, jade halls and frozen pond", k=1)
    assert exact[0][0].scene_id == "moon_palace"
    assert exact[0][1] == pytest.approx(1.0, abs=1e-6)


def test_reuse_rate_aggregate(svc: SceneLibrarySvc) -> None:
    """REQ-SCN-005 anchor: reuse rate computed from log."""

    desc = "A traditional tea house at dawn, lanterns swaying, plum blossoms outside"
    for _ in range(3):
        svc.decide_reuse(desc, scale="medium")
    svc.decide_reuse("A futuristic spaceport", scale="medium")
    rate = svc.reuse_rate()
    assert 0.5 < rate <= 1.0


def test_query_empty_library_returns_empty() -> None:
    s = SceneLibrarySvc()
    assert s.query("hello") == []
    d = s.decide_reuse("hello")
    assert d.reuse is False and d.matched_scene_id is None


def test_duplicate_scene_rejected(svc: SceneLibrarySvc) -> None:
    with pytest.raises(ValueError):
        svc.add_scene("tea_house_dawn", "duplicate")
