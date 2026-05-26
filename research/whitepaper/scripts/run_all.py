"""Run every model in `research.whitepaper.models` and emit:

- ``data/computed/*.json`` — one file per model
- ``figures/*.png`` — 10 charts (mpl deterministic)
- ``reports/whitepaper.md`` — auto-generated report

Reproducible:
    SEED=20260526 python -m research.whitepaper.scripts.run_all
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless on Windows / CI

import matplotlib.pyplot as plt  # noqa: E402  -- after backend pin
import numpy as np  # noqa: E402

from research.whitepaper import SEED  # noqa: E402
from research.whitepaper.models import (  # noqa: E402
    _io,
    consistency_model,
    cost_model,
    moderation_layered,
    pareto_frontier,
    pilot_calibration,
    repair_convergence,
    scene_reuse_marginal,
    seven_dim_qa_model,
    sla_model,
    throughput_model,
)


def _seed(args_seed: int | None) -> int:
    return int(args_seed if args_seed is not None else os.environ.get("MANHUAJU_WP_SEED", SEED))


def _make_rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _figure(save_path: Path) -> None:
    save_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(save_path, dpi=140)
    plt.close()


def _fig_cost_breakdown(out: dict[str, object]) -> None:
    tier_m = out["tier_M"]  # type: ignore[index]
    stages = tier_m["stages"]  # type: ignore[index]
    names = [s["name"] for s in stages]
    vals = [s["with_retry_cny"] for s in stages]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(names, vals)
    ax.set_xlabel("CNY per episode (with retry factor)")
    ax.set_title("Per-episode cost breakdown — Tier M (Manhuaju Agent fast 720p)")
    ax.axvline(80.0, color="r", linestyle="--", label="need.md anchor: ≤ ¥80")
    ax.legend()
    _figure(_io.FIGURES_DIR / "fig01_cost_breakdown.png")


def _fig_throughput_curve(rng: np.random.Generator) -> None:
    arrivals = np.linspace(2, 30, 60)
    rho = []
    wq = []
    manhuaju = _io.load_pricing("volcengine_manhuaju_2026").payload
    median_per_shot = manhuaju["endpoints"]["video_generate_fast720p"]["median_latency_s"]
    mean_render = median_per_shot * 18 / max(manhuaju["concurrency_quota"]["default"], 1)
    for a in arrivals:
        st = throughput_model.steady_state(a, mean_render, servers=manhuaju["concurrency_quota"]["default"])
        rho.append(st.rho)
        wq.append(min(st.wq_seconds, 3600))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(arrivals, rho, label="ρ utilisation")
    ax.set_xlabel("Arrivals (episodes/hour)")
    ax.set_ylabel("ρ")
    ax2 = ax.twinx()
    ax2.plot(arrivals, wq, color="orange", label="W_q (s)")
    ax2.set_ylabel("Expected wait (s, capped 3600)")
    ax.axhline(0.85, color="r", linestyle="--", label="ρ=0.85 target")
    ax.set_title("M/M/16 — utilisation vs arrival rate")
    fig.legend(loc="upper left")
    _figure(_io.FIGURES_DIR / "fig02_throughput.png")


def _fig_sla_episode(rng: np.random.Generator, sla_out: dict[str, object]) -> None:
    n = 50_000
    bench = _io.load_bench("stage_latency_priors").payload
    samples = np.zeros(n)
    parallel = {"video_generate": 16, "character_generate": 8, "scene_generate": 8}
    counts = {
        "script_analysis": 1,
        "character_generate": 4,
        "scene_generate": 6,
        "storyboard_generate": 1,
        "video_generate": 18,
        "video_compose": 1,
        "tts_generation": 1,
        "bgm_alignment": 1,
        "qa_seven_dim": 1,
        "moderation_dual": 1,
        "distribution_pack": 1,
    }
    for stage, cnt in counts.items():
        row = bench[bench["stage"] == stage].iloc[0]
        s = rng.lognormal(float(row["mu_log"]), float(row["sigma_log"]), n)
        rounds = int(np.ceil(cnt / parallel.get(stage, 1)))
        per_round = s
        for _ in range(rounds - 1):
            per_round = per_round + rng.lognormal(float(row["mu_log"]), float(row["sigma_log"]), n)
        samples = samples + per_round
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(np.minimum(samples / 60.0, 180), bins=80)
    ax.set_xlabel("Episode wall-clock (minutes)")
    ax.set_ylabel("Frequency")
    ax.axvline(60, color="r", linestyle="--", label="need.md anchor: P95 ≤ 60min")
    p95 = float(np.quantile(samples, 0.95) / 60.0)
    ax.axvline(p95, color="g", linestyle="-", label=f"observed P95 = {p95:.1f}min")
    ax.set_title("End-to-end episode latency distribution (10⁵ MC)")
    ax.legend()
    _figure(_io.FIGURES_DIR / "fig03_sla_episode.png")


def _fig_consistency(out: dict[str, object]) -> None:
    refresh_levels = [3, 5, 10, 60]
    leads = [out[f"lead_refresh_{r}"]["window5_mean"] for r in refresh_levels]  # type: ignore[index]
    leads_lo = [out[f"lead_refresh_{r}"]["window5_mean_lower_ci"] for r in refresh_levels]  # type: ignore[index]
    supports = [out[f"support_refresh_{r}"]["window5_mean"] for r in refresh_levels]  # type: ignore[index]
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(refresh_levels))
    width = 0.35
    ax.bar(x - width / 2, leads, width, yerr=[np.array(leads) - np.array(leads_lo), [0] * len(leads)], label="Lead")
    ax.bar(x + width / 2, supports, width, label="Support")
    ax.axhline(0.92, color="r", linestyle="--", label="lead anchor: ≥ 0.92")
    ax.axhline(0.88, color="orange", linestyle="--", label="support anchor: ≥ 0.88")
    ax.set_xticks(x)
    ax.set_xticklabels([f"every {r} ep" for r in refresh_levels])
    ax.set_ylim(0.80, 1.00)
    ax.set_ylabel("ArcFace 5-ep window mean")
    ax.set_title("Consistency vs anchor-frame refresh cadence")
    ax.legend()
    _figure(_io.FIGURES_DIR / "fig04_consistency.png")


def _fig_repair_convergence(out: dict[str, object]) -> None:
    p_grid = [0.50, 0.65, 0.75, 0.85, 0.92]
    n_grid = [2, 3, 4, 5]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for n in n_grid:
        ys = [out[f"p_{p}_n_{n}"]["expected_attempts"] for p in p_grid]  # type: ignore[index]
        ax.plot(p_grid, ys, marker="o", label=f"max_attempts = {n}")
    ax.set_xlabel("P(pass per attempt)")
    ax.set_ylabel("E[attempts]")
    ax.set_title("Repair-loop expected iterations")
    ax.legend()
    _figure(_io.FIGURES_DIR / "fig05_repair_convergence.png")


def _fig_seven_dim(out: dict[str, object]) -> None:
    thrs = [7.0, 7.5, 8.0, 8.5, 9.0]
    rates = [out[f"threshold_{t}"]["pass_rate"] for t in thrs]  # type: ignore[index]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(thrs, rates, marker="o")
    ax.axhline(0.85, color="r", linestyle="--", label="anchor ≥ 0.85")
    ax.axvline(8.0, color="g", linestyle="--", label="anchor threshold")
    ax.set_xlabel("Per-dim threshold")
    ax.set_ylabel("All-dim pass rate")
    ax.set_title("7-dim QA pass-rate vs threshold (Beta MC)")
    ax.legend()
    _figure(_io.FIGURES_DIR / "fig06_seven_dim.png")


def _fig_scene_reuse(out: dict[str, object]) -> None:
    sizes = [10, 25, 50, 100, 200, 500, 1000]
    saving = [
        next(c for c in out["curve"] if c["library_size"] == s)["saving_per_ep_cny"]  # type: ignore[index]
        for s in sizes
    ]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(sizes, saving, marker="o")
    ax.set_xscale("log")
    ax.set_xlabel("Scene library size")
    ax.set_ylabel("Per-episode CNY saved")
    ax.set_title("Scene-library reuse marginal savings")
    _figure(_io.FIGURES_DIR / "fig07_scene_reuse.png")


def _fig_pareto(out: dict[str, object]) -> None:
    pts = out["all_candidates"]  # type: ignore[index]
    front = out["frontier"]  # type: ignore[index]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter([p["cost_cny"] for p in pts], [p["latency_s"] / 60 for p in pts], alpha=0.4, label="candidates")
    ax.scatter(
        [p["cost_cny"] for p in front],
        [p["latency_s"] / 60 for p in front],
        color="red",
        marker="*",
        s=120,
        label="Pareto frontier",
    )
    ax.set_xlabel("Cost per episode (CNY)")
    ax.set_ylabel("Latency P95 (minutes)")
    ax.set_title("Cost vs Latency Pareto frontier (quality-coloured)")
    ax.legend()
    _figure(_io.FIGURES_DIR / "fig08_pareto.png")


def _fig_calibration(params: pilot_calibration.CalibratedParams) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    metrics = ["cost", "latency_min", "arcface", "p_pass"]
    vals = [
        params.cost_per_episode_cny,
        params.latency_episode_p95_s / 60.0,
        params.arcface_intra_mean,
        params.p_pass_per_attempt,
    ]
    cis = [
        (params.cost_per_episode_cny_ci95[1] - params.cost_per_episode_cny_ci95[0]) / 2,
        (params.latency_episode_p95_s_ci95[1] - params.latency_episode_p95_s_ci95[0]) / 120.0,
        (params.arcface_intra_mean_ci95[1] - params.arcface_intra_mean_ci95[0]) / 2,
        (params.p_pass_ci95[1] - params.p_pass_ci95[0]) / 2,
    ]
    ax.errorbar(metrics, vals, yerr=cis, fmt="o", capsize=5)
    ax.set_title(f"Pilot calibration (n={params.n_pilot_episodes}, status={params.calibration_status})")
    ax.set_ylabel("value")
    _figure(_io.FIGURES_DIR / "fig09_pilot_calibration.png")


def _fig_three_ips(rng: np.random.Generator) -> None:
    """Scenario comparison: bestseller vs avg vs flop in cost-latency space."""

    scenarios = {
        "bestseller_60ep": dict(target_seconds=120, n_characters=8, n_scenes=12, dialogue_chars=4500),
        "average_60ep": dict(target_seconds=90, n_characters=4, n_scenes=6, dialogue_chars=3000),
        "flop_30ep": dict(target_seconds=60, n_characters=3, n_scenes=4, dialogue_chars=2000),
    }
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, kw in scenarios.items():
        for tier in ("H", "M", "L"):
            ec = cost_model.per_episode_cost(tier=tier, **kw)
            ax.scatter(ec.total_with_retry_cny, len(name), label=f"{name} / {tier}")
    ax.set_xlabel("CNY per episode")
    ax.set_yticks([])
    ax.set_title("Three-IP scenario cost comparison (H / M / L tiers)")
    ax.legend(fontsize=7, loc="upper right", ncol=3)
    _figure(_io.FIGURES_DIR / "fig10_three_ips.png")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run all whitepaper models")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--skip-figures", action="store_true")
    args = parser.parse_args(argv)
    seed = _seed(args.seed)
    rng = _make_rng(seed)

    _io.COMPUTED_DIR.mkdir(parents=True, exist_ok=True)
    _io.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if not args.skip_figures:
        _io.FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. pilot calibration first (others read its JSON)
    calib_params = pilot_calibration.calibrate(rng)
    pilot_calibration.write_calibrated_params(calib_params)

    # 2. independent models (each gets its own rng spawn so they don't perturb each other)
    cost_out = cost_model.all_tiers_summary(rng.spawn(1)[0])
    _io.write_computed("cost", cost_out)

    thr_out = throughput_model.summary()
    _io.write_computed("throughput", thr_out)

    sla_out = sla_model.episode_latency_distribution(rng.spawn(1)[0])
    _io.write_computed("sla", sla_out)

    cons_out = consistency_model.summary(rng.spawn(1)[0])
    _io.write_computed("consistency", cons_out)

    sd_out = seven_dim_qa_model.summary(rng.spawn(1)[0])
    _io.write_computed("seven_dim_qa", sd_out)

    rep_out = repair_convergence.summary()
    _io.write_computed("repair", rep_out)

    sr_out = scene_reuse_marginal.summary()
    _io.write_computed("scene_reuse", sr_out)

    mod_out = moderation_layered.summary(rng.spawn(1)[0])
    _io.write_computed("moderation", mod_out)

    par_out = pareto_frontier.summary(rng.spawn(1)[0])
    _io.write_computed("pareto", par_out)

    if not args.skip_figures:
        _fig_cost_breakdown(cost_out)
        _fig_throughput_curve(rng.spawn(1)[0])
        _fig_sla_episode(rng.spawn(1)[0], sla_out)
        _fig_consistency(cons_out)
        _fig_repair_convergence(rep_out)
        _fig_seven_dim(sd_out)
        _fig_scene_reuse(sr_out)
        _fig_pareto(par_out)
        _fig_calibration(calib_params)
        _fig_three_ips(rng.spawn(1)[0])

    write_report(seed, calib_params, cost_out, sla_out, cons_out, sd_out, thr_out, rep_out, sr_out, mod_out, par_out)
    print(f"[whitepaper] computed dir: {_io.COMPUTED_DIR}")
    print(f"[whitepaper] figures dir : {_io.FIGURES_DIR}")
    print(f"[whitepaper] report file : {_io.REPORTS_DIR / 'whitepaper.md'}")
    return 0


def write_report(
    seed: int,
    calib: pilot_calibration.CalibratedParams,
    cost_out: dict[str, object],
    sla_out: dict[str, object],
    cons_out: dict[str, object],
    sd_out: dict[str, object],
    thr_out: dict[str, object],
    rep_out: dict[str, object],
    sr_out: dict[str, object],
    mod_out: dict[str, object],
    par_out: dict[str, object],
) -> None:
    rep_path = _io.REPORTS_DIR / "whitepaper.md"
    lines: list[str] = []
    lines.append("# Manhuaju Autopilot v2.0 — Quantitative Whitepaper (auto-generated)\n")
    lines.append(f"> seed = `{seed}` · calibration_status = `{calib.calibration_status}` · n_pilot_episodes = {calib.n_pilot_episodes}\n")
    lines.append("\n## 1. Headline Numbers\n")
    tier_m = cost_out["tier_M"]  # type: ignore[index]
    lines.append(f"- Per-episode cost (Tier M, mean): **¥{tier_m['mc_mean']:.2f}**, P95 = ¥{tier_m['mc_p95']:.2f} (anchor ≤ ¥80)")
    lines.append(f"- Episode P95 latency: **{sla_out['episode']['p95_s'] / 60:.1f} min** (anchor ≤ 60min)")  # type: ignore[index]
    lines.append(f"- Cross-ep ArcFace lead window-5 mean: **{cons_out['lead_refresh_5']['window5_mean']:.4f}** (anchor ≥ 0.92)")  # type: ignore[index]
    lines.append(f"- 7-dim QA pass rate @ threshold 8.0: **{sd_out['threshold_8.0']['pass_rate']:.4f}**")  # type: ignore[index]
    lines.append(f"- Episodes/hour at default c=16: **{thr_out['episodes_per_hour_at_default_c']:.2f}** (anchor ≥ 8)")
    lines.append(f"- Repair retry factor (recommended): **{rep_out['recommended_default']['retry_factor']:.3f}**")  # type: ignore[index]
    lines.append(f"- Moderation FNR (AND, doubao_pro CI95 upper): **{mod_out['doubao_pro']['fnr_and_ci95_upper']:.6f}**")  # type: ignore[index]
    lines.append("\n## 2. Files\n")
    for name in (
        "cost",
        "sla",
        "consistency",
        "seven_dim_qa",
        "throughput",
        "repair",
        "scene_reuse",
        "moderation",
        "pareto",
        "calibrated_params",
    ):
        lines.append(f"- `data/computed/{name}.json`")
    lines.append("\n## 3. Anchor compliance\n")
    anchors = [
        ("Cost ≤ ¥80", tier_m["mc_p95"] <= 80.0),  # type: ignore[index]
        ("Episode P95 ≤ 60 min", sla_out["episode"]["p95_s"] <= 3600.0),  # type: ignore[index]
        ("ArcFace lead ≥ 0.92", cons_out["lead_refresh_5"]["window5_mean"] >= 0.92),  # type: ignore[index]
        ("ArcFace support ≥ 0.88", cons_out["support_refresh_5"]["window5_mean"] >= 0.88),  # type: ignore[index]
        ("Episodes/hr ≥ 8", thr_out["episodes_per_hour_at_default_c"] >= 8.0),
        ("Image P95 ≤ 15s", sla_out["image_generation"]["p95_s"] <= 15.0),  # type: ignore[index]
        ("Video 5s P95 ≤ 180s", sla_out["video_5s"]["p95_s"] <= 180.0),  # type: ignore[index]
        ("First-token P95 ≤ 5s", sla_out["first_token"]["p95_s"] <= 5.0),  # type: ignore[index]
    ]
    for label, ok in anchors:
        lines.append(f"- {'✅' if ok else '❌'} {label}")
    rep_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
