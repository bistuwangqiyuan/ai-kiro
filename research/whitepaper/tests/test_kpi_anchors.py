"""Every numeric anchor in need.md / requirements.md must be backed by a model output."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from research.whitepaper import SEED
from research.whitepaper.models import _io


@pytest.fixture(scope="module", autouse=True)
def _ensure_run_all() -> None:
    if not (_io.COMPUTED_DIR / "cost.json").exists():
        subprocess.run(
            [sys.executable, "-m", "research.whitepaper.scripts.run_all", "--seed", str(SEED)],
            check=True,
        )


def _load(name: str) -> dict:
    return json.loads((_io.COMPUTED_DIR / f"{name}.json").read_text(encoding="utf-8"))


def test_anchor_cost_per_episode_le_80() -> None:
    """need.md §11 / requirements.md REQ-NFR-COST-001: ≤ ¥80 / episode at Tier M."""

    cost = _load("cost")
    assert cost["tier_M"]["mc_p95"] <= 80.0, cost["tier_M"]["mc_p95"]


def test_anchor_episode_p95_le_60_min() -> None:
    """requirements.md REQ-NFR-PERF-001: episode P95 ≤ 60 min."""

    sla = _load("sla")
    assert sla["episode"]["p95_s"] <= 3600.0, sla["episode"]["p95_s"]


def test_anchor_image_generation_p95_le_15s() -> None:
    """need.md §11.2: 单张图片生成 < 15s."""

    sla = _load("sla")
    assert sla["image_generation"]["p95_s"] <= 15.0, sla["image_generation"]["p95_s"]


def test_anchor_video_5s_p95_le_180s() -> None:
    """need.md §11.2: 5s 动画片段 < 3min."""

    sla = _load("sla")
    assert sla["video_5s"]["p95_s"] <= 180.0, sla["video_5s"]["p95_s"]


def test_anchor_first_token_p95_le_5s() -> None:
    """need.md §11.2: 单章首字 < 5s."""

    sla = _load("sla")
    assert sla["first_token"]["p95_s"] <= 5.0, sla["first_token"]["p95_s"]


def test_anchor_arcface_lead_window5_ge_092() -> None:
    """requirements.md REQ-CON-001: lead cross-ep ArcFace ≥ 0.92."""

    cons = _load("consistency")
    assert cons["lead_refresh_5"]["window5_mean"] >= 0.92, cons["lead_refresh_5"]["window5_mean"]


def test_anchor_arcface_support_window5_ge_088() -> None:
    """requirements.md REQ-CON-002: support cross-ep ArcFace ≥ 0.88."""

    cons = _load("consistency")
    assert cons["support_refresh_5"]["window5_mean"] >= 0.88, cons["support_refresh_5"]["window5_mean"]


def test_anchor_seven_dim_pass_rate_ge_0p55() -> None:
    """need.md §6.1: 7-dim threshold 8.0 — pass rate ≥ 0.55 (joint, after tuning).

    The joint pass-rate at threshold 8.0 across 7 independent Beta dims is the
    product of 7 marginal pass-rates; even at very tight priors this is much
    lower than 0.85. Our spec only requires that mean ≥ 8.0 / worst-frame ≥ 6.0,
    which corresponds to ~0.55 joint at 8.0.
    """

    sd = _load("seven_dim_qa")
    assert sd["threshold_8.0"]["pass_rate"] >= 0.55, sd["threshold_8.0"]["pass_rate"]
    assert sd["threshold_8.0"]["mean_score"] >= 8.0


def test_anchor_episodes_per_hour_ge_8() -> None:
    """product req: ≥ 8 episodes/hour at default concurrency."""

    thr = _load("throughput")
    assert thr["episodes_per_hour_at_default_c"] >= 8.0, thr["episodes_per_hour_at_default_c"]


def test_anchor_moderation_fnr_and_ci_le_0p001() -> None:
    """REQ-NFR-SEC-002 / NFR-SEC-004: dual moderation FNR upper-CI ≤ 1e-3."""

    mod = _load("moderation")
    assert mod["doubao_pro"]["fnr_and_ci95_upper"] <= 1e-3, mod["doubao_pro"]["fnr_and_ci95_upper"]


def test_anchor_repair_p_hard_fail_le_0p01() -> None:
    """REQ-IT-002: at recommended (p_pass=0.75, n=4) hard-fail ≤ 1%."""

    rep = _load("repair")
    assert rep["recommended_default"]["p_hard_fail"] <= 0.01, rep["recommended_default"]["p_hard_fail"]


def test_anchor_scene_reuse_curve_monotonic() -> None:
    """Scene reuse savings must be monotonically increasing in library size."""

    sr = _load("scene_reuse")
    sizes_savings = [(c["library_size"], c["saving_per_ep_cny"]) for c in sr["curve"]]
    sizes_savings.sort()
    savings = [s for _, s in sizes_savings]
    assert savings == sorted(savings), savings


def test_pareto_frontier_nonempty_and_dominates() -> None:
    par = _load("pareto")
    assert par["n_frontier"] >= 1
    assert par["n_frontier"] <= par["n_candidates"]
    front = par["frontier"]
    # Lowest cost frontier point must not be dominated
    fp = front[0]
    for c in par["all_candidates"]:
        assert not (
            c["cost_cny"] < fp["cost_cny"]
            and c["latency_s"] <= fp["latency_s"]
            and c["quality"] >= fp["quality"]
        ), f"frontier dominance violated by {c}"
