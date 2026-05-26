"""Generate 10 minimal Jupyter notebooks that reproduce the whitepaper figures.

Each notebook loads the corresponding `data/computed/*.json` produced by
``run_all`` and re-creates its figure inline. This keeps the repo lean —
notebooks are *thin* views; the heavy lifting lives in ``models/``.
"""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent / "notebooks"
NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)


def cell_md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def cell_code(source: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "outputs": [],
        "execution_count": None,
        "source": source.splitlines(keepends=True),
    }


def make_notebook(cells: list[dict]) -> dict:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


PREAMBLE = (
    "from pathlib import Path\n"
    "import json, numpy as np, matplotlib.pyplot as plt\n"
    "ROOT = Path('..').resolve() if Path('..').name == 'whitepaper' else Path('.').resolve().parent\n"
    "COMPUTED = ROOT / 'data' / 'computed'\n"
    "FIGURES = ROOT / 'figures'\n"
    "def load(name): return json.loads((COMPUTED / f'{name}.json').read_text(encoding='utf-8'))\n"
)

NOTEBOOKS: list[tuple[str, str, str, str]] = [
    (
        "01_pricing_landscape.ipynb",
        "Pricing Landscape (Volcengine Manhuaju + Skylark + Seedance)",
        "Snapshot of upstream prices used by every other notebook.",
        "for f in (ROOT / 'data' / 'pricing').glob('*.json'):\n"
        "    print(f.name)\n"
        "    print(json.dumps(json.loads(f.read_text(encoding='utf-8')), indent=2, ensure_ascii=False)[:500])\n"
        "    print('-' * 40)\n",
    ),
    (
        "02_cost_per_episode.ipynb",
        "Per-episode cost — Tier H/M/L decomposition",
        "12-stage cost breakdown for default 60s episode at scene_reuse=0.40, retry_factor=0.18.",
        "cost = load('cost')\nfor tier in ('H', 'M', 'L'):\n"
        "    print(tier, 'mean =', cost[f'tier_{tier}']['mc_mean'], 'p95 =', cost[f'tier_{tier}']['mc_p95'])\n"
        "stages = cost['tier_M']['stages']\n"
        "names = [s['name'] for s in stages]\n"
        "vals = [s['with_retry_cny'] for s in stages]\n"
        "fig, ax = plt.subplots(figsize=(9, 4.5))\n"
        "ax.barh(names, vals); ax.axvline(80, color='r', linestyle='--', label='need.md ≤ ¥80')\n"
        "ax.set_xlabel('CNY/episode'); ax.set_title('Tier M cost decomposition'); ax.legend(); plt.tight_layout(); plt.show()\n",
    ),
    (
        "03_throughput_queue.ipynb",
        "M/M/16 throughput",
        "Episodes/hour saturation curve and steady-state utilisation.",
        "thr = load('throughput'); print('eps/hr default c=', thr['episodes_per_hour_at_default_c'])\n"
        "lambdas = [k for k in thr if k.startswith('lambda_')]\n"
        "rho = [thr[k]['rho'] for k in lambdas]\n"
        "wq = [min(thr[k]['wq_seconds_expected_wait'], 3600) for k in lambdas]\n"
        "vals = [int(k.split('_')[1]) for k in lambdas]\n"
        "fig, ax = plt.subplots(figsize=(8,4))\n"
        "ax.plot(vals, rho, marker='o', label='ρ'); ax2 = ax.twinx(); ax2.plot(vals, wq, marker='s', color='orange', label='Wq (s)')\n"
        "ax.axhline(0.85, color='r', linestyle='--'); ax.set_xlabel('arrivals/hour'); ax.set_title('M/M/c saturation'); plt.tight_layout(); plt.show()\n",
    ),
    (
        "04_consistency_drift.ipynb",
        "Cross-episode ArcFace drift Markov",
        "Identity drift trajectories with anchor-frame refresh every K episodes.",
        "cons = load('consistency')\n"
        "for r in (3,5,10,60):\n"
        "    print('lead refresh',r,'->', cons[f'lead_refresh_{r}']['window5_mean'])\n"
        "import matplotlib.pyplot as plt\n"
        "x = [3,5,10,60]\n"
        "y_lead = [cons[f'lead_refresh_{r}']['window5_mean'] for r in x]\n"
        "y_sup = [cons[f'support_refresh_{r}']['window5_mean'] for r in x]\n"
        "plt.plot(x, y_lead, marker='o', label='lead'); plt.plot(x, y_sup, marker='s', label='support')\n"
        "plt.axhline(0.92, color='r', linestyle='--'); plt.xlabel('refresh every K ep'); plt.legend(); plt.show()\n",
    ),
    (
        "05_repair_convergence.ipynb",
        "Repair-loop convergence (truncated geometric)",
        "Expected attempts and hard-fail rate vs (p_pass, max_attempts).",
        "rep = load('repair'); print(rep['recommended_default'])\n"
        "for k,v in rep.items():\n"
        "    if k.startswith('p_'):\n"
        "        print(k, v['expected_attempts'], v['p_hard_fail'])\n",
    ),
    (
        "06_seven_dim_qa.ipynb",
        "7-dim QA pass-rate (Beta MC)",
        "Per-dimension and joint pass rate at threshold ∈ {7.0,7.5,8.0,8.5,9.0}.",
        "sd = load('seven_dim_qa')\n"
        "thrs = [7.0,7.5,8.0,8.5,9.0]; rates = [sd[f'threshold_{t}']['pass_rate'] for t in thrs]\n"
        "plt.plot(thrs, rates, marker='o'); plt.axhline(0.85, color='r', linestyle='--'); plt.show()\n"
        "print('mean per dim @ t=8.0:', sd['threshold_8.0']['mean_per_dim'])\n",
    ),
    (
        "07_scene_reuse_economics.ipynb",
        "Scene-library reuse marginal savings",
        "saving_per_ep_cny vs library_size on log-x.",
        "sr = load('scene_reuse'); print('library_size_for_90pct =', sr['library_size_for_90pct'])\n"
        "sizes = [c['library_size'] for c in sr['curve']]\n"
        "save = [c['saving_per_ep_cny'] for c in sr['curve']]\n"
        "plt.plot(sizes, save, marker='o'); plt.xscale('log'); plt.xlabel('library size'); plt.ylabel('CNY saved'); plt.show()\n",
    ),
    (
        "08_pareto_frontier.ipynb",
        "Cost vs Latency vs Quality Pareto frontier",
        "36 candidate points; non-dominated subset highlighted.",
        "par = load('pareto')\n"
        "all_c = par['all_candidates']; front = par['frontier']\n"
        "plt.scatter([c['cost_cny'] for c in all_c], [c['latency_s']/60 for c in all_c], alpha=0.4)\n"
        "plt.scatter([c['cost_cny'] for c in front], [c['latency_s']/60 for c in front], color='red', marker='*', s=120)\n"
        "plt.xlabel('CNY/ep'); plt.ylabel('P95 latency (min)'); plt.title('Pareto frontier'); plt.show()\n"
        "for f in front: print(f)\n",
    ),
    (
        "09_pilot_calibration.ipynb",
        "Pilot calibration & 95% CI",
        "Reads `calibrated_params.json` (synthetic until 3-ep pilot is run).",
        "p = load('calibrated_params')\nfor k in ('cost_per_episode_cny', 'latency_episode_p95_s', 'arcface_intra_mean', 'p_pass_per_attempt'):\n"
        "    print(k, p[k], p.get(k+'_ci95'))\n",
    ),
    (
        "10_three_ips_comparison.ipynb",
        "Three-IP scenario comparison (bestseller / average / flop)",
        "Cost-Latency for three production scales × three tiers.",
        "import sys; sys.path.insert(0, str(ROOT.parent.parent))\n"
        "from research.whitepaper.models import cost_model\n"
        "scenarios = {\n"
        "    'bestseller': dict(target_seconds=120, n_characters=8, n_scenes=12, dialogue_chars=4500),\n"
        "    'average':    dict(target_seconds=90,  n_characters=4, n_scenes=6,  dialogue_chars=3000),\n"
        "    'flop':       dict(target_seconds=60,  n_characters=3, n_scenes=4,  dialogue_chars=2000),\n"
        "}\n"
        "for name, kw in scenarios.items():\n"
        "    for tier in ('H','M','L'):\n"
        "        ec = cost_model.per_episode_cost(tier=tier, **kw)\n"
        "        print(name, tier, '->', round(ec.total_with_retry_cny,2))\n",
    ),
]


def main() -> int:
    for fname, title, intro, code in NOTEBOOKS:
        nb = make_notebook(
            [
                cell_md(f"# {title}\n"),
                cell_md(f"_{intro}_\n\n> Reproducible from `data/computed/*.json` written by `run_all.py`.\n"),
                cell_code(PREAMBLE),
                cell_code(code),
            ]
        )
        path = NOTEBOOKS_DIR / fname
        path.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"[notebooks] wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
