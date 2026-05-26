# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com) and the project uses
[Semantic Versioning](https://semver.org).

## [v2.0.0] — 2026-05-26

### Highlights

The v2.0 release implements the **need.md V3.0 Final** specification end-to-end:

* **Spec rewrite**: `requirements.md`, `design.md`, `tasks.md` upgraded with 13 new
  REQ clusters (≥ 70 EARS), 22 Agents + 11 Services topology, 8 new data models,
  and Epic 9 with 11 stories / ≥ 70 leaf tasks.
* **Quantitative whitepaper** (`research/whitepaper/`): 10 mathematical models
  (cost / throughput / SLA / consistency / 7-dim QA / repair convergence /
  scene reuse / moderation / Pareto / pilot calibration), 10 notebooks,
  10 figures, all byte-identical reproducible at `seed=20260526`.
* **11 new modules** wired into the existing 4-step Volcengine pipeline via
  `pipelines.v2_enrichment` pre-/post-flight passes.
* **Three-episode mock pilot** with reverse calibration — 95% CI upper bounds
  for cost / latency / ArcFace are all asserted against need.md anchors.

### Added

#### Modules (11 new services)

* `manhuaju.api.mode_router` + `web/simple.html` + `web/pro.html` + `config/modes.yaml`
* `manhuaju.services.storyboard_grid` + `manhuaju.services.grid_renderer` (9-25 cell)
* `manhuaju.services.emotion_library` + `manhuaju.services.emotion_injection`
* `manhuaju.services.action_library` + `manhuaju.adapters.pose.{mock,real_dwpose}_adapter`
* `manhuaju.services.outfit_change` + `manhuaju.services.season_dynasty_matcher`
* `manhuaju.services.scene_library` + `manhuaju.adapters.embedding.scene_index_adapter`
* `manhuaju.services.style_transfer` + `manhuaju.adapters.styletransfer.{mock,real_seedream_styletx}_adapter`
* `manhuaju.services.transmedia_ingest` + `manhuaju.services.keyframe_extractor`
* `manhuaju.services.music_alignment` + `manhuaju.services.auto_cut`
* `manhuaju.services.distribution_pack` + `manhuaju.services.watermark` + `manhuaju.services.copy_style_router`
* `manhuaju.services.template_engine` + `config/templates/{cdrama_classic,sweet_pet,xianxia_epic}.yaml`

#### Pipeline glue

* `manhuaju.pipelines.v2_enrichment` — pre-/post-flight passes around the
  existing `ManhuajuAgentPipeline`. Layer-clean (import-linter passes).

#### Tests

* `tests/unit/test_mode_router.py` (9), `test_grid.py` (14),
  `test_emotion_lib.py` (13), `test_action_lib.py` (13),
  `test_outfit_change.py` (12), `test_scene_library.py` (12),
  `test_style_transfer.py` (10), `test_transmedia.py` (13),
  `test_auto_cut.py` (11), `test_distribution_pack.py` (10),
  `test_template_engine.py` (12).
* `tests/integration/test_v2_enrichment.py` (5).
* `tests/e2e_three_episodes/test_post_calibration.py` (7).
* All v2 modules pass `ruff check`, `mypy --ignore-missing-imports`, and
  `import-linter` (layered architecture).

#### Quantitative whitepaper

* `research/whitepaper/models/{cost,throughput,sla,consistency,seven_dim_qa,
   repair_convergence,scene_reuse_marginal,moderation_layered,pareto_frontier,
   pilot_calibration}.py`
* `research/whitepaper/scripts/{run_all,calibrate_from_pilot,sensitivity_1k}.py`
* `research/whitepaper/tests/{test_determinism,test_kpi_anchors,
   test_pilot_calibration_ci}.py`
* `research/whitepaper/notebooks/*.ipynb` (10 notebooks)
* `research/whitepaper/figures/*.png` (10 figures)
* `research/whitepaper/data/{pricing,benchmarks,computed}/`

#### Documentation

* README.md v2.0 section with module table + reproduction recipe.
* `.kiro/specs/ai-manhuaju-autopilot/{requirements,design,tasks}.md` v2.0
  with new sections §23 / §19 / Epic 9.

### Changed

* `requirements.md` version bumped to `2.0.0`; appended §23 with 13 REQ clusters
  and a quantitative-anchoring appendix.
* `design.md` version bumped to `2.0.0`; appended §19 with the 22 Agents +
  11 Services topology and 8 new data models.
* `tasks.md` version bumped to `2.0.0`; appended Epic 9 with 11 stories.

### Notes

* No breaking API changes — the v4 small-bird Agent 2.0 path remains the
  primary live path; v2.0 services run as orthogonal enrichment.
* `seed=20260526` is the global lock for the whitepaper. Bumping it requires
  a full re-run + figure refresh.
