# Manhuaju Autopilot v2.0 — Quantitative Whitepaper (auto-generated)

> seed = `20260526` · calibration_status = `synthetic_preliminary` · n_pilot_episodes = 3


## 1. Headline Numbers

- Per-episode cost (Tier M, mean): **¥71.53**, P95 = ¥78.53 (anchor ≤ ¥80)
- Episode P95 latency: **14.2 min** (anchor ≤ 60min)
- Cross-ep ArcFace lead window-5 mean: **0.9288** (anchor ≥ 0.92)
- 7-dim QA pass rate @ threshold 8.0: **0.7551**
- Episodes/hour at default c=16: **362.67** (anchor ≥ 8)
- Repair retry factor (recommended): **0.328**
- Moderation FNR (AND, doubao_pro CI95 upper): **0.000843**

## 2. Files

- `data/computed/cost.json`
- `data/computed/sla.json`
- `data/computed/consistency.json`
- `data/computed/seven_dim_qa.json`
- `data/computed/throughput.json`
- `data/computed/repair.json`
- `data/computed/scene_reuse.json`
- `data/computed/moderation.json`
- `data/computed/pareto.json`
- `data/computed/calibrated_params.json`

## 3. Anchor compliance

- ✅ Cost ≤ ¥80
- ✅ Episode P95 ≤ 60 min
- ✅ ArcFace lead ≥ 0.92
- ✅ ArcFace support ≥ 0.88
- ✅ Episodes/hr ≥ 8
- ✅ Image P95 ≤ 15s
- ✅ Video 5s P95 ≤ 180s
- ✅ First-token P95 ≤ 5s