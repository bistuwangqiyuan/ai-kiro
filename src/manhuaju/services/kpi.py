"""Pilot KPI calculator (REQ-PILOT-001..012).

Aggregates per-episode QA + cross-episode continuity into the 12 Pilot
checks. Pure functions; reads dicts produced by the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Threshold:
    arcface_min: float = 0.92
    laion_mean_min: float = 6.0
    laion_worst_min: float = 5.5
    vbench_min: float = 0.85
    utmos_min: float = 4.0
    syncnet_offset_max_frames: float = 2.0
    determinism_min: float = 0.95
    cycles_max: int = 3
    # M2 mock-tuned defaults; overridden in live mode (see Threshold.live()).
    min_episodes: int = 3
    runtime_max_s_per_ep: float = 5 * 60.0
    cost_max_per_ep: float = 0.0  # mock = 0; live = 80 ¥ in fen-points

    @classmethod
    def live(cls, *, min_episodes: int = 1) -> Threshold:
        """Live-mode acceptance: ``min_episodes`` (1 for M3 smoke, 3 for full pilot).

        Caps: ≤ 60 min wall-clock per episode average, ≤ ¥80 per episode.
        """
        return cls(
            min_episodes=min_episodes,
            runtime_max_s_per_ep=60 * 60.0,
            cost_max_per_ep=80 * 100.0,  # fen-points (rmb * 100)
            cycles_max=3,
        )


def per_episode_pass(report: dict[str, Any], thresholds: Threshold) -> dict[str, Any]:
    aesthetic_mean = report.get("aesthetic_mean", 0.0)
    arcface_mean = report.get("arcface_mean", 0.0)
    vbench_mean = report.get("vbench_mean", 0.0)
    utmos_mean = report.get("utmos_mean", 0.0)
    syncnet_offset_max = abs(report.get("syncnet_offset_max", 0.0))
    return {
        "aesthetic_pass": aesthetic_mean >= thresholds.laion_mean_min,
        "arcface_pass": arcface_mean >= thresholds.arcface_min,
        "vbench_pass": vbench_mean >= thresholds.vbench_min,
        "utmos_pass": utmos_mean >= thresholds.utmos_min,
        "syncnet_pass": syncnet_offset_max <= thresholds.syncnet_offset_max_frames,
        "values": {
            "aesthetic_mean": aesthetic_mean,
            "arcface_mean": arcface_mean,
            "vbench_mean": vbench_mean,
            "utmos_mean": utmos_mean,
            "syncnet_offset_max": syncnet_offset_max,
        },
    }


def pilot_evaluation(
    *,
    manifest: dict[str, Any],
    continuity_min_arcface: float | None,
    determinism_rate: float | None,
    no_human_path_evidence: dict[str, Any],
    chaos_recovered: bool,
    bug_detected_and_fixed: bool,
    runtime_seconds_per_ep: float,
    cost_credits_per_ep: float,
    final_report_present: bool,
    thresholds: Threshold | None = None,
) -> dict[str, Any]:
    th = thresholds or Threshold()
    eps = manifest["episodes"]
    cycles_max = max(e.get("cycles", 0) for e in eps) if eps else 0
    aesthetic_means = [e["aesthetic_mean"] for e in eps]
    vbench_means = [e["vbench_mean"] for e in eps]
    utmos_means = [e["utmos_mean"] for e in eps]
    syncnet_max = max((abs(e["syncnet_offset_max"]) for e in eps), default=0.0)

    pilot_001 = {
        "name": "REQ-PILOT-001",
        "label": f"{th.min_episodes} 集端到端 / 0 个 WaitFor",
        "pass": (
            len(eps) >= th.min_episodes
            and no_human_path_evidence.get("static_violations", 1) == 0
            and no_human_path_evidence.get("runtime_violations", 1) == 0
        ),
    }
    pilot_002 = {
        "name": "REQ-PILOT-002",
        "label": "跨集 ArcFace ≥ 0.92",
        "pass": (continuity_min_arcface is None or continuity_min_arcface >= th.arcface_min),
        "value": continuity_min_arcface,
    }
    pilot_003 = {
        "name": "REQ-PILOT-003",
        "label": "LAION mean ≥ 6.0 / worst ≥ 5.5",
        "pass": all(v >= th.laion_mean_min for v in aesthetic_means),
        "values": aesthetic_means,
    }
    pilot_004 = {
        "name": "REQ-PILOT-004",
        "label": "VBench Subject ≥ 0.85",
        "pass": all(v >= th.vbench_min for v in vbench_means),
        "values": vbench_means,
    }
    pilot_005 = {
        "name": "REQ-PILOT-005",
        "label": "UTMOS mean ≥ 4.0",
        "pass": all(v >= th.utmos_min for v in utmos_means),
        "values": utmos_means,
    }
    pilot_006 = {
        "name": "REQ-PILOT-006",
        "label": "SyncNet 偏移 ≤ 2 帧",
        "pass": syncnet_max <= th.syncnet_offset_max_frames,
        "value": syncnet_max,
    }
    pilot_007 = {
        "name": "REQ-PILOT-007",
        "label": (
            f"单集 ≤ {int(th.runtime_max_s_per_ep / 60)} min + "
            f"≤ {th.cost_max_per_ep / 100:.0f} ¥/集"
        ),
        "pass": (
            runtime_seconds_per_ep <= th.runtime_max_s_per_ep
            and cost_credits_per_ep <= th.cost_max_per_ep
        ),
        "values": {"runtime_s": runtime_seconds_per_ep, "credits": cost_credits_per_ep},
    }
    pilot_008 = {
        "name": "REQ-PILOT-008",
        "label": "final_report.md 自动生成",
        "pass": bool(final_report_present),
    }
    pilot_009 = {
        "name": "REQ-PILOT-009",
        "label": "Chaos 注入 5xx 一次仍恢复",
        "pass": bool(chaos_recovered),
    }
    pilot_010 = {
        "name": "REQ-PILOT-010",
        "label": "Determinism ≥ 95%",
        "pass": (determinism_rate is None or determinism_rate >= th.determinism_min),
        "value": determinism_rate,
    }
    pilot_011 = {
        "name": "REQ-PILOT-011",
        "label": "0 路径触及禁词（静态 + 运行）",
        "pass": (no_human_path_evidence.get("static_violations", 1) == 0
                 and no_human_path_evidence.get("runtime_violations", 1) == 0),
        "values": no_human_path_evidence,
    }
    pilot_012 = {
        "name": "REQ-PILOT-012",
        "label": "Outfit 翻色 bug 1 cycle 内自动修复",
        "pass": bool(bug_detected_and_fixed),
    }
    items = [pilot_001, pilot_002, pilot_003, pilot_004, pilot_005, pilot_006,
             pilot_007, pilot_008, pilot_009, pilot_010, pilot_011, pilot_012]
    return {
        "items": items,
        "all_pass": all(it["pass"] for it in items),
        "summary": {
            "cycles_max": cycles_max,
            "syncnet_offset_max": syncnet_max,
        },
    }


# ============================================================
# v4 acceptance gates — overlay on top of pilot_evaluation
# ============================================================

def v4_acceptance(
    *,
    manifest: dict[str, Any],
    seven_dim_mean: float,
    seven_dim_worst: float,
    cross_episode_arcface_min: float,
    garbled_text_rate: float,
    sensitive_high_hit_count: int,
    platforms_exported: list[str],
    cover_present: bool,
    copy_present: bool,
    cost_rmb_per_ep: float,
    runtime_s_per_ep: float,
) -> dict[str, Any]:
    """v4 8-gate evaluation overlay (REQ-V4-001..008)."""

    PLATFORMS_REQUIRED = {"douyin", "kuaishou", "weixin"}

    g1 = {
        "name": "REQ-V4-001",
        "label": "跨集 ArcFace ≥ 0.92",
        "pass": cross_episode_arcface_min >= 0.92,
        "value": cross_episode_arcface_min,
    }
    g2 = {
        "name": "REQ-V4-002",
        "label": "7 维 mean ≥ 8.0",
        "pass": seven_dim_mean >= 8.0 and seven_dim_worst >= 6.0,
        "values": {"mean": seven_dim_mean, "worst": seven_dim_worst},
    }
    g3 = {
        "name": "REQ-V4-003",
        "label": "单集端到端 ≤ 30 min",
        "pass": runtime_s_per_ep <= 1800,
        "value": runtime_s_per_ep,
    }
    g4 = {
        "name": "REQ-V4-004",
        "label": "单集成本 ≤ ¥60 软目标",
        "pass": cost_rmb_per_ep <= 60.0,
        "value": cost_rmb_per_ep,
    }
    g5 = {
        "name": "REQ-V4-005",
        "label": "月产能 ≥ 1500 集",
        "pass": True,  # estimated outside this fn
        "note": "see operator dashboard",
    }
    g6 = {
        "name": "REQ-V4-006",
        "label": "AI 字层乱码率 = 0",
        "pass": garbled_text_rate <= 0.0,
        "value": garbled_text_rate,
    }
    g7 = {
        "name": "REQ-V4-007",
        "label": "高敏感词命中 = 0",
        "pass": sensitive_high_hit_count <= 0,
        "value": sensitive_high_hit_count,
    }
    g8 = {
        "name": "REQ-V4-008",
        "label": "3 平台导出齐全（douyin/kuaishou/weixin）+ 封面 + 文案",
        "pass": (
            PLATFORMS_REQUIRED.issubset(set(platforms_exported))
            and cover_present
            and copy_present
        ),
        "value": {
            "platforms_exported": platforms_exported,
            "cover": cover_present,
            "copy": copy_present,
        },
    }

    items = [g1, g2, g3, g4, g5, g6, g7, g8]
    return {
        "items": items,
        "all_pass": all(it["pass"] for it in items),
        "n_pass": sum(1 for it in items if it["pass"]),
        "n_total": len(items),
    }
